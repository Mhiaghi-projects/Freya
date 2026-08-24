"""app/api/storage.py:_build_tree -- árbol de hasta 3 niveles de
profundidad desde un prefijo (pedido explícito del usuario, botón "ver
árbol de directorios"), construido sobre la lista plana que devuelve
storage."""

from __future__ import annotations

from app.api.storage import _build_tree


def _objs(*keys: str) -> list[dict]:
    return [{"key": k} for k in keys]


def test_archivos_sueltos_en_la_raiz() -> None:
    tree = _build_tree(_objs("u1/a.txt", "u1/b.txt"), "u1/")
    assert tree == [
        {"name": "a.txt", "type": "file"},
        {"name": "b.txt", "type": "file"},
    ]


def test_agrupa_subcarpetas() -> None:
    tree = _build_tree(_objs("u1/docs/a.txt", "u1/docs/b.txt", "u1/c.txt"), "u1/")
    assert tree == [
        {"name": "docs", "type": "folder", "children": [
            {"name": "a.txt", "type": "file"},
            {"name": "b.txt", "type": "file"},
        ]},
        {"name": "c.txt", "type": "file"},
    ]


def test_ignora_los_placeholders_de_carpeta_vacia() -> None:
    tree = _build_tree(_objs("u1/vacia/.keep"), "u1/")
    assert tree == [{"name": "vacia", "type": "folder", "children": []}]


def test_corta_en_3_niveles_de_profundidad() -> None:
    # u1/a/b/c/d.txt tiene 4 niveles bajo el prefijo (a, b, c, d.txt) --
    # el 3er nivel ("c") se muestra como carpeta vacía en el árbol, sin
    # bajar a un 4to.
    tree = _build_tree(_objs("u1/a/b/c/d.txt"), "u1/")
    assert tree == [
        {"name": "a", "type": "folder", "children": [
            {"name": "b", "type": "folder", "children": [
                {"name": "c", "type": "folder", "children": []},
            ]},
        ]},
    ]


def test_ordena_carpetas_antes_que_archivos_y_alfabeticamente() -> None:
    tree = _build_tree(_objs("u1/z.txt", "u1/carpeta/x.txt", "u1/a.txt"), "u1/")
    names = [(n["name"], n["type"]) for n in tree]
    assert names == [("carpeta", "folder"), ("a.txt", "file"), ("z.txt", "file")]


def test_clave_sin_el_prefijo_se_usa_tal_cual() -> None:
    # No debería pasar en la práctica (storage ya filtra por prefix), pero
    # si llegara una clave que no empieza con el prefijo pedido, se trata
    # como ruta completa en vez de reventar.
    tree = _build_tree(_objs("otro/a.txt"), "u1/")
    assert tree == [
        {"name": "otro", "type": "folder", "children": [
            {"name": "a.txt", "type": "file"},
        ]},
    ]
