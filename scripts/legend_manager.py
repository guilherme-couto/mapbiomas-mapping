"""
MÓDULO: legend_manager.py
Objetivo: Carregar coleções de legendas em formato JSON e resolver a
          hierarquia de classes de forma automática e dinâmica.
"""

import json
from pathlib import Path
import numpy as np


class LegendManager:
    def __init__(self, caminho_json: Path):
        if not caminho_json.exists():
            raise FileNotFoundError(f"Arquivo de legenda não encontrado: {caminho_json}")

        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)

        self.nome_colecao = dados.get("name", caminho_json.stem)
        # Indexa as classes pelo seu class_id numérico
        self.classes_por_id = {c["id"]: c for c in dados["classes"]}

    def resolver_ancestral(self, id_orig: int, nivel_alvo: int) -> int:
        """
        Sobe a árvore hierárquica a partir do parent_id até que o nível
        seja menor ou igual ao nível alvo escolhido (1, 2, 3 ou 4).
        """
        if id_orig not in self.classes_por_id:
            return id_orig  # Retorna o ID original se for classe não catalogada

        atual = self.classes_por_id[id_orig]

        # Sobe os níveis enquanto o nível atual for mais detalhado que o desejado
        while atual["level"] > nivel_alvo and atual["parent_id"] is not None:
            id_pai = atual["parent_id"]
            if id_pai not in self.classes_por_id:
                break
            atual = self.classes_por_id[id_pai]

        return atual["id"]

    def reclassificar_matriz(self, matriz_raster: np.ndarray, nivel_alvo: int) -> np.ndarray:
        """ Gera uma nova matriz reclassificada com base no nível alvo. """
        ids_presentes = np.unique(matriz_raster)
        matriz_saida = np.zeros_like(matriz_raster)

        for id_val in ids_presentes:
            if id_val == 0:
                continue
            alvo_id = self.resolver_ancestral(int(id_val), nivel_alvo)
            matriz_saida[matriz_raster == id_val] = alvo_id

        return matriz_saida

    def obter_info_classes(self, matriz_reclassificada: np.ndarray) -> dict:
        """ Recupera nomes e cores das classes que de fato estão presentes na imagem. """
        ids_unicos = np.unique(matriz_reclassificada)
        ids_validos = sorted([int(i) for i in ids_unicos if i != 0])

        info = {}
        for cid in ids_validos:
            if cid in self.classes_por_id:
                info[cid] = {
                    "name_pt": self.classes_por_id[cid]["name_pt"],
                    "hex_code": self.classes_por_id[cid]["hex_code"]
                }
            else:
                info[cid] = {
                    "name_pt": f"Classe {cid}",
                    "hex_code": "#888888"
                }
        return info