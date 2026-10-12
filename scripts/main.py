"""
Mapeamento de Uso e Cobertura - MapBiomas (Pipeline Modular)
================================================================================
Fluxo de execução:
1. Lê as configurações do arquivo TOML
2. Carrega o gerenciador de legendas JSON
3. Carrega o vetor de interesse (shapefile, GeoJSON ou GeoPackage)
4. Recorte do GeoTIFF de entrada com resolução controlada
5. Reclassificação hierárquica (Níveis 1 a 4 via LegendManager)
6. Geração do mapa estático (PNG ou SVG)
7. Opcionais: - Exportação do GeoTIFF reclassificado
              - Exportação do mapa web interativo (HTML)
================================================================================
"""

import argparse
from pathlib import Path
import sys
import tomllib

# Garante que os módulos locais em scripts/ sejam encontrados
diretorio_scripts = Path(__file__).resolve().parent
if str(diretorio_scripts) not in sys.path:
    sys.path.append(str(diretorio_scripts))

from map_utils import carregar_vetor, recortar_raster_por_vetor, gerar_mapa_estatico
from export_geotiff import salvar_geotiff
from export_html import salvar_mapa_html
from legend_manager import LegendManager


def parse_args(diretorio_raiz: Path) -> argparse.Namespace:
    """Configura e interpreta os argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Processamento de dados de uso e cobertura do MapBiomas com corte vetorial e reclassificação."
    )
    parser.add_argument(
        "-c", "--config",
        dest="caminho_config",
        type=Path,
        default=diretorio_raiz / "configs" / "config.toml",
        help="Caminho para o arquivo de configuração TOML (Padrão: configs/config.toml)."
    )
    return parser.parse_args()


# ==============================================================================
# CARREGA CONFIGURAÇÃO DO USUÁRIO
# ==============================================================================
def carregar_configuracoes(caminho_toml: Path) -> dict:
    if not caminho_toml.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {caminho_toml}")
    with open(caminho_toml, "rb") as f:
        return tomllib.load(f)
    
    
# ==============================================================================
# FLUXO PRINCIPAL DE EXECUÇÃO
# ==============================================================================
def main():
    print("PROCESSAMENTO MAPBIOMAS - USO E COBERTURA")
    
    diretorio_raiz = Path(__file__).resolve().parent.parent
    
    # 1. Carrega configurações externas
    print("\n[1/6] Carregando arquivo de configuração...")
    args = parse_args(diretorio_raiz)
    caminho_config = args.caminho_config.resolve()
    if not caminho_config.exists():
        print(f"ERRO: Arquivo de configuração não encontrado em: {caminho_config}")
        print("-> Copie o arquivo 'configs/example.toml' para 'config.toml' e edite conforme necessário.")
        return
    cfg = carregar_configuracoes(caminho_config)

    c_dados = cfg["dados_entrada"]
    c_mapa = cfg["mapa_estatico"]
    c_exp = cfg["exportacoes_opcionais"]

    # Definição de caminhos
    caminho_geotiff = diretorio_raiz / "inputs" / "geotiff" / c_dados["geotiff_entrada"]
    caminho_vetor = diretorio_raiz / "inputs" / "vector" / c_dados["vetor_corte"]
    caminho_legenda = diretorio_raiz / "legends" / f"{c_dados['colecao_legenda']}.json"

    # 2. Carrega o gerenciador de legendas JSON
    print("\n[2/6] Carregando regras de legenda e hierarquia...")
    if not caminho_legenda.exists():
        print(f"ERRO: Arquivo de legenda não encontrado em: {caminho_legenda}")
        return
    gerenciador_legenda = LegendManager(caminho_legenda)

    # 3. Carrega o vetor de interesse
    print("\n[3/6] Carregando vetor da área de estudo...")
    if not caminho_vetor.exists():
        print(f"ERRO: Vetor não encontrado em: {caminho_vetor}")
        return
    gdf_area = carregar_vetor(caminho_vetor)

    # 4. Recorta o GeoTIFF pela extensão do vetor
    print("\n[4/6] Recortando raster pelo polígono do vetor...")
    if not caminho_geotiff.exists():
        print(f"ERRO: GeoTIFF de entrada não encontrado em: {caminho_geotiff}")
        return
    (
        matriz_recortada,
        perfil,
        gdf_reprojetado,
        crs_raster
    ) = recortar_raster_por_vetor(
        caminho_geotiff,
        gdf_area,
        resolucao_metros=c_dados['resolucao_metros']
    )

    # 5. Aplica reclassificação hierárquica automática
    print(f"\n[5/6] Reclassificando para o Nível {c_dados['nivel_hierarquico']} do MapBiomas...")
    matriz_reclassificada = gerenciador_legenda.reclassificar_matriz(
        matriz_recortada,
        nivel_alvo=c_dados['nivel_hierarquico']
    )
    classes_info = gerenciador_legenda.obter_info_classes(matriz_reclassificada)

    print(f"-> Classes detectadas na área ({len(classes_info)}):")
    for cid, info in classes_info.items():
        print(f"   - ID {cid:>2}: {info['name_pt']} (Cor: {info['hex_code']})")

    # 6. Gera o mapa estático (PNG ou SVG)
    print("\n[6/6] Renderizando mapa cartográfico estático...")
    c_mapa["level"] = c_dados["nivel_hierarquico"]
    nome_fig = f"mapa_{Path(c_dados["vetor_corte"]).stem}_{Path(c_dados["geotiff_entrada"]).stem}_nivel_{c_dados['nivel_hierarquico']}.{c_mapa['formato_figura']}"
    caminho_saida_fig = diretorio_raiz / "outputs" / "figs" / nome_fig
    gerar_mapa_estatico(
        caminho_saida=caminho_saida_fig,
        matriz_dados=matriz_reclassificada,
        perfil=perfil,
        classes_info=classes_info,
        gdf_vetor=gdf_reprojetado,
        config=c_mapa
    )

    # 7. Exportações complementares
    if c_exp["exportar_geotiff"] or c_exp["exportar_html"]:
        print("\n[Extra] Processando exportações opcionais...")
            
    if c_exp["exportar_geotiff"]:
        nome_tif = f"{Path(c_dados["vetor_corte"]).stem}_{Path(c_dados["geotiff_entrada"]).stem}_nivel_{c_dados['nivel_hierarquico']}.tif"
        caminho_saida_tif = diretorio_raiz / "outputs" / "geotiff" / nome_tif
        salvar_geotiff(caminho_saida_tif, matriz_reclassificada, perfil)

    if c_exp["exportar_html"]:
        nome_html = f"mapa_interativo_{Path(c_dados["vetor_corte"]).stem}_{Path(c_dados["geotiff_entrada"]).stem}_nivel_{c_dados['nivel_hierarquico']}.html"
        caminho_saida_html = diretorio_raiz / "outputs" / "html" / nome_html
        salvar_mapa_html(
            caminho_saida=caminho_saida_html,
            matriz_dados=matriz_reclassificada,
            perfil_metadados=perfil,
            classes_info=classes_info,
            gdf_area=gdf_reprojetado,
            resolucao_metros=c_dados['resolucao_metros']
        )

    print("\nPROCESSAMENTO CONCLUÍDO COM SUCESSO!")


if __name__ == "__main__":
    main()