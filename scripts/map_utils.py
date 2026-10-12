"""
MÓDULO: map_utils.py
Objetivo: Funções utilitárias geoespaciais e cartográficas (leitura de vetores,
          recorte com reamostragem via VRT e geração de mapa estático em alta resolução).
"""

from pathlib import Path
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.patches as mpatches


def carregar_vetor(caminho_vetor: Path) -> gpd.GeoDataFrame:
    """Carrega vetores nos formatos Shapefile (.shp), GeoPackage (.gpkg) ou GeoJSON (.geojson/.json)."""
    if not caminho_vetor.exists():
        raise FileNotFoundError(f"Arquivo vetorial não encontrado: {caminho_vetor}")
    print(f"-> Carregando vetor de corte: {caminho_vetor.name}")
    gdf = gpd.read_file(caminho_vetor)
    return gdf


def recortar_raster_por_vetor(caminho_geotiff: Path, gdf: gpd.GeoDataFrame, resolucao_metros: float = 30.0):
    """ Recorta o GeoTIFF pelo vetor de interesse com controle de resolução espacial em metros.  """
    print(f"-> Abrindo GeoTIFF base: {caminho_geotiff.name}")
    with rasterio.open(caminho_geotiff) as src:
        # Reprojeta o vetor caso o CRS seja diferente do GeoTIFF
        if gdf.crs != src.crs:
            print(f"-> Reprojetando vetor de {gdf.crs} para {src.crs}...")
            gdf = gdf.to_crs(src.crs)

        geometrias = [geom for geom in gdf.geometry if geom is not None]

        # Resolução nativa em metros
        res_nativa_m = abs(src.transform[0]) * 111320.0 if src.crs.is_geographic else abs(src.transform[0])

        if resolucao_metros <= (res_nativa_m * 1.05):
            print(f"-> Usando resolução nativa do MapBiomas (~{res_nativa_m:.1f} m)...")
            matriz_recortada, transform_recortada = mask(src, geometrias, crop=True, nodata=0)
            perfil = src.meta.copy()
        else:
            print(f"-> Aplicando reamostragem exata para {resolucao_metros:.1f} m...")
            minx, miny, maxx, maxy = gdf.total_bounds

            # Converte metros para unidades de projeção (graus ou metros)
            res_unidade = (resolucao_metros / 111320.0) if src.crs.is_geographic else resolucao_metros
            nova_largura = max(int(np.ceil((maxx - minx) / res_unidade)), 1)
            nova_altura = max(int(np.ceil((maxy - miny) / res_unidade)), 1)

            # Matriz afim a partir da Bounding Box real
            nova_transform = rasterio.transform.from_bounds(
                minx, miny, maxx, maxy, nova_largura, nova_altura
            )

            with WarpedVRT(
                src,
                resampling=Resampling.nearest,
                transform=nova_transform,
                width=nova_largura,
                height=nova_altura
            ) as vrt:
                matriz_recortada, transform_recortada = mask(vrt, geometrias, crop=True, nodata=0)
                perfil = vrt.meta.copy()

        perfil.update({
            "height": matriz_recortada.shape[1],
            "width": matriz_recortada.shape[2],
            "transform": transform_recortada,
            "nodata": 0
        })

        crs_raster = src.crs

    return matriz_recortada[0], perfil, gdf, crs_raster


# ==============================================================================
# ELEMENTOS CARTOGRÁFICOS AUXILIARES
# ==============================================================================
def _avaliar_ocupacao_cantos(matriz_dados: np.ndarray) -> dict:
    """
    Calcula a densidade de pixels preenchidos (diferentes de zero) em uma
    janela de 25% em cada um dos 4 cantos da matriz.
    """
    h, w = matriz_dados.shape
    f_h = max(int(h * 0.25), 1)
    f_w = max(int(w * 0.25), 1)

    cantos = {
        "bottom-right": np.count_nonzero(matriz_dados[-f_h:, -f_w:]),
        "bottom-left": np.count_nonzero(matriz_dados[-f_h:, :f_w]),
        "top-right": np.count_nonzero(matriz_dados[:f_h, -f_w:]),
        "top-left": np.count_nonzero(matriz_dados[:f_h, :f_w])
    }
    return cantos


def _determinar_posicoes_otimas(matriz_dados: np.ndarray, posicao_preferencial: str = "auto") -> str:
    """
    Determina o canto com maior espaço livre (menor contagem de pixels)
    para alocar o bloco conjunto (rosa dos ventos + barra de escala).
    """
    if posicao_preferencial != "auto":
        return posicao_preferencial

    ocupacao = _avaliar_ocupacao_cantos(matriz_dados)

    # Ordem cartográfica de preferência em caso de empate de vazios
    ordem_preferencia = ["bottom-right", "bottom-left", "top-right", "top-left"]
    ordem_preferencia.sort(key=lambda canto: ocupacao[canto])

    return ordem_preferencia[0]


def _adicionar_rosa_dos_ventos(ax, posicao: str = "bottom-right"):
    """
    Desenha a rosa dos ventos
    """
    x_centro = 0.8 if "right" in posicao else 0.2

    # Cotas verticais relativas calculadas para ficar logo acima da escala
    if "top" in posicao:
        y_texto_n = 0.865
        y_haste = 0.890
        y_ponta = 0.930
    else:
        y_texto_n = 0.105
        y_haste = 0.130
        y_ponta = 0.170

    # Rótulo 'N' centralizado
    ax.text(
        x_centro,
        y_texto_n,
        "N",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=10,
        fontweight="bold",
        color="#111111",
        zorder=6
    )

    # Seta apontando para o Norte
    ax.annotate(
        "",
        xy=(x_centro, y_ponta),
        xytext=(x_centro, y_haste),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops=dict(
            facecolor="#111111",
            edgecolor="#111111",
            width=2.4,
            headwidth=7,
            headlength=8
        ),
        zorder=6
    )


def _adicionar_barra_escala(ax, west, east, south, north, crs, posicao: str = "bottom-right"):
    """
    Desenha a barra de escala
    """
    largura_unidades = east - west
    lat_media = (north + south) / 2.0

    if crs and crs.is_geographic:
        km_por_unidade = 111.32 * np.cos(np.radians(lat_media))
        largura_total_km = largura_unidades * km_por_unidade
    else:
        km_por_unidade = 0.001
        largura_total_km = largura_unidades / 1000.0

    tamanho_alvo_km = largura_total_km / 5.0
    escalas = [1, 2, 5, 10, 25, 50, 100, 200, 250, 500, 1000]
    comprimento_km = min(escalas, key=lambda x: abs(x - tamanho_alvo_km))
    comprimento_no_eixo = comprimento_km / km_por_unidade

    xlim = ax.get_xlim()
    largura_quadro = xlim[1] - xlim[0]
    largura_frac = comprimento_no_eixo / largura_quadro

    # Eixo central idêntico ao da rosa dos ventos
    x_centro = 0.8 if "right" in posicao else 0.2

    if "top" in posicao:
        y_linha = 0.815
        y_texto = 0.827
    else:
        y_linha = 0.055
        y_texto = 0.067

    # Linha da escala distribuída simetricamente em torno de x_centro
    x_ini = x_centro - (largura_frac / 2.0)
    x_fim = x_centro + (largura_frac / 2.0)

    # Linha da barra
    ax.plot(
        [x_ini, x_fim],
        [y_linha, y_linha],
        transform=ax.transAxes,
        color="#111111",
        lw=3.2,
        zorder=6
    )

    # Texto da distância centralizado sobre a linha
    ax.text(
        x_centro,
        y_texto,
        f"{comprimento_km:g} km",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        fontweight="bold",
        color="#111111",
        zorder=6
    )


def gerar_mapa_estatico(
    caminho_saida: Path,
    matriz_dados: np.ndarray,
    perfil: dict,
    classes_info: dict,
    gdf_vetor: gpd.GeoDataFrame,
    config: dict
) -> None:
    """Gera o mapa cartográfico estático em formato PNG ou SVG"""
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    print(f"-> Gerando mapa estático em: {caminho_saida.resolve()}")

    ids_ordenados = sorted(classes_info.keys())
    cores_hex = [classes_info[i]["hex_code"] for i in ids_ordenados]

    cmap = ListedColormap(cores_hex)
    bounds = [ids_ordenados[0] - 0.5] + [i + 0.5 for i in ids_ordenados]
    norm = BoundaryNorm(bounds, cmap.N)

    # Torna pixels sem dados (0) transparentes
    dados_mascarados = np.ma.masked_where(matriz_dados == 0, matriz_dados)

    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)

    transform = perfil["transform"]
    h, w = matriz_dados.shape
    west = transform[2]
    north = transform[5]
    east = west + transform[0] * w
    south = north + transform[4] * h
    extent = [west, east, south, north]

    # 1. Renderiza o raster
    ax.imshow(dados_mascarados, cmap=cmap, norm=norm, extent=extent, interpolation="nearest")

    # 2. Simplificação visual do contorno vetorial para evitar sobrecarga de renderização
    tolerancia = 0.005 if perfil["crs"].is_geographic else 500.0
    gdf_plot = gdf_vetor.copy()
    gdf_plot["geometry"] = gdf_plot.geometry.simplify(tolerance=tolerancia, preserve_topology=True)
    gdf_plot.boundary.plot(ax=ax, color="#222222", linewidth=1.0, zorder=3)

    # 3. Delimitação dos eixos: dimensão + margem para enquadramento visual
    margem = 0.025 * max(east - west, north - south)
    ax.set_xlim(west - margem, east + margem)
    ax.set_ylim(south - margem, north + margem)

    # Ajusta o aspecto para projeção geográfica correta (evita esticar no sentido norte-sul)
    if perfil["crs"].is_geographic:
        lat_media = (north + south) / 2.0
        ax.set_aspect(1.0 / np.cos(np.radians(lat_media)))

    # 4. Título
    if config.get("show_title", True):
        ax.set_title(
            f"MapBiomas: Uso e Cobertura da Terra",
            fontsize=12,
            fontweight="bold",
            pad=12
        )

    # 5. Coordenadas e Linhas de Grade
    if config.get("show_gridlines", False):
        ax.grid(True, linestyle="--", alpha=0.3, color="#888888")
        ax.set_xlabel("Longitude (°)", fontsize=9)
        ax.set_ylabel("Latitude (°)", fontsize=9)
        ax.tick_params(labelsize=8)
    else:
        ax.grid(False)

    if not config.get("show_lat_lon_labels", True):
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("")
        ax.set_ylabel("")
    else:
        ax.set_xlabel("Longitude (°)", fontsize=9)
        ax.set_ylabel("Latitude (°)", fontsize=9)
        ax.tick_params(labelsize=8)

    ax.tick_params(axis="both", which="both", length=0)

    # 6. Legenda
    if config.get("show_legend", True):
        patches = [
            mpatches.Patch(color=classes_info[cid]["hex_code"], label=classes_info[cid]["name_pt"])
            for cid in ids_ordenados
        ]
        ax.legend(
            handles=patches,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            title=f"Classes (Nível {config.get('level', 1)})",
            title_fontsize="9",
            alignment="left",
            fontsize=8,
            frameon=True,
            facecolor="#fafafa",
            edgecolor="#cccccc"
        )

    # Posicionamento automático da barra de escala e da rosa dos ventos
    posicao_conjunta = _determinar_posicoes_otimas(
        matriz_dados,
        posicao_preferencial=config.get("elements_loc", "auto")
    )

    # 7. Rosa dos Ventos
    if config.get("show_north_arrow", True):
        _adicionar_rosa_dos_ventos(ax, posicao=posicao_conjunta)

    # 8. Barra de Escala
    if config.get("show_scale_bar", True):
        _adicionar_barra_escala(ax, west, east, south, north, perfil["crs"], posicao=posicao_conjunta)

    # 9. Moldura do mapa
    if not config.get("show_frame", True):
        for pos in ["right", "top", "bottom", "left"]:
            ax.spines[pos].set_visible(False)

    # 10. Salva a figura com enquadramento ajustado
    fig.savefig(
        caminho_saida,
        format=config.get("fig_format", "png"),
        dpi=300,
        bbox_inches="tight"
    )
    plt.close(fig)
    print("Mapa estático salvo com sucesso!")