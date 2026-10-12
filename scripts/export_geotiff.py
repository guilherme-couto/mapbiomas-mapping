"""
MÓDULO: export_geotiff.py
Objetivo: Fornecer funções para exportação de dados matriciais (rasters)
          no formato GeoTIFF com georreferenciamento e compressão.
"""

from pathlib import Path
import rasterio
from rasterio.enums import Resampling


def salvar_geotiff(
    caminho_saida: Path,
    matriz_dados,
    perfil_metadados: dict,
    valor_nodata: int = 0
) -> None:
    """
    Salva uma matriz 2D numpy como GeoTIFF georreferenciado.

    Parâmetros:
    -----------
    caminho_saida : Path
        Caminho completo de destino (incluindo nome e extensão .tif).
    matriz_dados : numpy.ndarray
        Matriz bidimensional (linhas, colunas) contendo os valores de pixel reclassificados.
    perfil_metadados : dict
        Dicionário com perfil geoespacial do Rasterio (CRS, transform, dimensões, etc.).
    valor_nodata : int, opcional
        Valor numérico que representará ausência de dados (padrão: 0).
    """
    # Garante que o diretório de destino exista
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    # Clona e atualiza os metadados do arquivo de saída
    metadados = perfil_metadados.copy()
    metadados.update({
        "driver": "GTiff",
        "height": matriz_dados.shape[0],
        "width": matriz_dados.shape[1],
        "count": 1,
        "dtype": matriz_dados.dtype,
        "nodata": valor_nodata,
        "compress": "lzw"  # Compressão sem perdas (reduz bastante o tamanho do arquivo)
    })

    print(f"-> Exportando GeoTIFF para: {caminho_saida.resolve()}")
    with rasterio.open(caminho_saida, "w", **metadados) as dst:
        dst.write(matriz_dados, 1)

    print("GeoTIFF exportado com sucesso!")