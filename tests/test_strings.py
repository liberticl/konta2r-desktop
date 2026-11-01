"""strings.py: todo texto visible sale de ahí, en es/en/pt, con descripción."""
import re

from konta2r import strings as lng


def test_idiomas_completos():
    assert set(lng.LANG_CODES) == {"es", "en", "pt"}
    assert lng.DEFAULT_LANG == "es"
    for key, entry in lng.STRINGS.items():
        assert set(entry) >= {"es", "en", "pt", "desc"}, f"{key} incompleto"
        for lang in ("es", "en", "pt"):
            assert entry[lang].strip(), f"{key}/{lang} vacío"
        assert entry["desc"].strip(), f"{key} sin descripción"


def test_tr_fallbacks():
    assert lng.t("no_existe") == "no_existe"
    assert lng.t("measure_start", "xx") == lng.STRINGS["measure_start"]["es"]
    assert lng.t("measure_done_log", "en", total=3) == \
        lng.STRINGS["measure_done_log"]["en"].format(total=3)
    assert lng.t("measure_done_log", "es")  # sin params no rompe el {total}


def test_clases_en_tres_idiomas():
    from konta2r import settings as st
    assert set(lng.CLASS_NAMES) == set(st.CLASS_KEYS)
    for key, entry in lng.CLASS_NAMES.items():
        for lang in ("es", "en", "pt"):
            assert entry[lang].strip(), f"clase {key}/{lang} vacía"
        assert entry["desc"].strip(), f"clase {key} sin descripción"


def test_todo_tr_usado_existe():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "konta2r" / "ui" / "app.py").read_text(encoding="utf-8")
    usados = set(re.findall(r"self\.tr\(\"([^\"]+)\"|lng\.t\(\"([^\"]+)\"", src))
    usados = {a or b for a, b in usados}
    assert usados, "no se encontró ningún self.tr() en la UI"
    faltan = usados - set(lng.STRINGS)
    assert not faltan, f"claves usadas sin definir: {faltan}"


def test_sin_hardcode_en_idioma_por_defecto():
    """El idioma por defecto también sale de strings (no 'es' suelto)."""
    import pathlib
    from konta2r import settings as st
    assert st.LANG_DEFAULT == lng.DEFAULT_LANG
    root = pathlib.Path(__file__).resolve().parent.parent / "konta2r"
    for f in list(root.glob("*.py")) + list((root / "ui").glob("*.py")):
        if f.name in ("strings.py",):
            continue
        src = f.read_text(encoding="utf-8")
        assert 'get("lang") or "es"' not in src, f"{f.name} hardcodea idioma"
