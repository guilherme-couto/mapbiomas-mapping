"""
MÓDULO: export_html.py
Objetivo: Gerar mapa interativo destacando em cores apenas os pixels da região de interesse.
"""

from pathlib import Path
import io
import base64
import numpy as np
from PIL import Image
import geopandas as gpd
import plotly.graph_objects as go


def _calcular_zoom_inicial(largura_graus: float, altura_graus: float) -> float:
    """Calcula o enquadramento ideal de zoom para a extensão territorial."""
    maior_extensao = max(largura_graus, altura_graus)
    if maior_extensao > 25:
        return 4.0
    elif maior_extensao > 12:
        return 5.0
    elif maior_extensao > 6:
        return 6.0
    elif maior_extensao > 2:
        return 7.5
    elif maior_extensao > 1:
        return 9.0
    return 10.5


def salvar_mapa_html(
    caminho_saida: Path,
    matriz_dados: np.ndarray,
    perfil_metadados: dict,
    classes_info: dict,
    gdf_area: gpd.GeoDataFrame = None,
    resolucao_metros: float = 30.0,
    valor_nodata: int = 0
) -> None:
    """Exporta o mapa interativo em HTML"""
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    print(f"-> Gerando mapa interativo em: {caminho_saida.resolve()}")

    h, w = matriz_dados.shape
    transform = perfil_metadados["transform"]
    west = transform[2]
    north = transform[5]
    east = west + transform[0] * w
    south = north + transform[4] * h

    # 1. Converte a matriz de classes do MapBiomas para imagem RGBA
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    for classe_id, info in classes_info.items():
        hex_color = info["hex_code"].lstrip("#")
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        mascara = (matriz_dados == classe_id)
        rgba[mascara] = [r, g, b, 240]  # Pixels de uso e cobertura com cor viva

    # Fora do corte, os pixels permanecem 100% transparentes
    # permitindo visualizar os países e oceanos vizinhos no estilo CARTO Positron
    rgba[matriz_dados == valor_nodata] = [0, 0, 0, 0]

    # Codifica a matriz em PNG Base64
    img_pil = Image.fromarray(rgba)
    buffer = io.BytesIO()
    img_pil.save(buffer, format="PNG", optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    img_uri = f"data:image/png;base64,{b64_str}"

    # 2. Vértices geográficos da camada [Top-Left, Top-Right, Bottom-Right, Bottom-Left]
    coordenadas_cantos = [
        [west, north],
        [east, north],
        [east, south],
        [west, south]
    ]

    centro_lat = (north + south) / 2.0
    centro_lon = (east + west) / 2.0
    zoom_inicial = _calcular_zoom_inicial(abs(east - west), abs(north - south))

    # 3. Compatibilidade universal de versões (Plotly 6+ e Plotly 5.x)
    if hasattr(go, "Scattermap"):
        ClasseScatter = go.Scattermap
        chave_mapa = "map"
    else:
        ClasseScatter = go.Scattermapbox
        chave_mapa = "mapbox"

    fig = go.Figure()

    # Adiciona itens na legenda lateral interativa
    for cid in sorted(classes_info.keys()):
        info = classes_info[cid]
        fig.add_trace(
            ClasseScatter(
                lat=[None],
                lon=[None],
                mode="markers",
                marker=dict(size=14, color=info["hex_code"]),
                name=info["name_pt"],
                showlegend=True
            )
        )

    # 4. Configuração com o estilo oficial 'carto-positron'
    configuracao_mapa = {
        "style": "carto-positron",  # Estilo com fundo mundial claro e sem chaves de API
        "center": dict(lat=centro_lat, lon=centro_lon),
        "zoom": zoom_inicial,
        "layers": [
            {
                "sourcetype": "image",
                "source": img_uri,
                "coordinates": coordenadas_cantos,
                "opacity": 1.0
            }
        ]
    }

    fig.update_layout(
        **{
            chave_mapa: configuracao_mapa,
            "margin": dict(r=0, t=35, l=0, b=0),
            "title": dict(
                text="MapBiomas: Uso e Cobertura da Terra",
                font=dict(size=15, color="#222222"),
                x=0.02,
                y=0.97
            ),
            "legend": dict(
                title=dict(text="<b>Classes MapBiomas</b>", font=dict(size=12)),
                bgcolor="rgba(255, 255, 255, 0.92)",
                bordercolor="#cccccc",
                borderwidth=1,
                orientation="v",
                yanchor="top",
                y=0.95,
                xanchor="left",
                x=0.01,
                itemclick=False,
                itemdoubleclick=False
            )
        }
    )

    fig.write_html(str(caminho_saida), include_plotlyjs="cdn")
    print("Mapa HTML interativo salvo com sucesso!")