"""Backend del panel nuevo (PRD #3 §7.7): servido en /panel, acciones permitidas y movimiento reversible."""
from estudia import clock
from estudia.web import panel as servidor

from .conftest import at, book
from .test_api import API, mundo, nuevo_cliente  # noqa: F401

# ------------------------------------------------------------------ servido de /panel

def _dist(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>PANEL</html>")
    (tmp_path / "assets" / "app-abc.js").write_text("console.log(1)")
    (tmp_path / "secreto.txt").write_text("no")
    monkeypatch.setattr(servidor, "DIST", tmp_path)
    return tmp_path


def test_panel_and_its_inner_routes_return_the_page(tmp_path, monkeypatch):
    _dist(tmp_path, monkeypatch)
    c = nuevo_cliente()
    for ruta in ("/panel", "/panel/", "/panel/agenda", "/panel/pacientes/12", "/panel/a/b/c"):
        r = c.get(ruta, follow_redirects=True)
        assert r.status_code == 200 and "PANEL" in r.text, ruta
    js = c.get("/panel/assets/app-abc.js")
    assert js.status_code == 200 and "immutable" in js.headers["cache-control"]
    assert c.get("/panel/index.html").headers["cache-control"] == "no-cache"


def test_panel_never_serves_files_outside_the_build(tmp_path, monkeypatch):
    base = _dist(tmp_path, monkeypatch)
    sub = base / "dist"
    sub.mkdir()
    (sub / "index.html").write_text("<html>PANEL</html>")
    monkeypatch.setattr(servidor, "DIST", sub)
    c = nuevo_cliente()
    for ruta in ("/panel/../secreto.txt", "/panel/%2e%2e/secreto.txt", "/panel/..%2fsecreto.txt"):
        r = c.get(ruta, follow_redirects=True)
        assert r.text != "no", ruta


def test_panel_rule_does_not_intercept_other_routes():
    c = nuevo_cliente()
    assert c.get("/docs").status_code == 200
    assert c.get("/api/v1/sesion").status_code == 401
    assert c.get("/agendar").status_code == 200
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 200 and "Blissens" in r.text  # la raíz es la landing pública, ya no redirige al panel
    assert c.get("/simulador").status_code == 200
    assert c.get("/static/inexistente.css").status_code == 404


def test_panel_without_build_says_which_command_to_run(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "DIST", tmp_path / "no-existe")
    r = nuevo_cliente().get("/panel/agenda")
    assert r.status_code == 503 and "make panel" in r.text


# ------------------------------------------------------------------ acciones permitidas

def _acciones(cli, cita_id, dia):
    ag = cli.get(f"{API}/agenda?desde={dia}&hasta={dia}").json()
    en_agenda = next(c["acciones"] for c in ag["citas"] if c["id"] == cita_id)
    assert cli.get(f"{API}/citas/{cita_id}").json()["acciones"] == en_agenda
    return en_agenda


def test_allowed_actions_follow_role_state_and_the_system_clock(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.commit()
    dia = at(1, "09:00").date()
    assert _acciones(mundo.aux, c, dia) == ["confirmar", "cancelar", "cambiar_fecha"]
    assert _acciones(mundo.esp1, c, dia) == []
    clock.freeze(at(1, "09:05"))
    assert _acciones(mundo.aux, c, dia) == ["desenlace"]
    assert _acciones(mundo.esp1, c, dia) == ["desenlace"]
    mundo.esp1.post(f"{API}/citas/{c}/desenlace", json={"desenlace": "atendida"})
    assert _acciones(mundo.aux, c, dia) == [] and _acciones(mundo.esp1, c, dia) == []


def test_cancelled_appointments_offer_no_actions(mundo, conn):
    from .test_api import motivo_id
    c = book(conn, mundo.p1, mundo.pro1, at(2, "09:00"))
    conn.commit()
    mundo.aux.post(f"{API}/citas/{c}/cancelar", json={"motivo_id": motivo_id(conn)})
    assert _acciones(mundo.aux, c, at(2, "09:00").date()) == []


# ------------------------------------------------------------------ movimiento reversible

def test_only_the_latest_movement_is_reversible_and_by_role(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.commit()
    clock.freeze(at(1, "09:30"))
    mundo.esp1.post(f"{API}/citas/{c}/desenlace", json={"desenlace": "no_asistio"})
    esp = mundo.esp1.get(f"{API}/citas/{c}").json()["historial"]
    assert [h["reversible"] for h in esp] == [False, True]
    aux = mundo.aux.get(f"{API}/citas/{c}").json()["historial"]
    assert [h["reversible"] for h in aux] == [False, True]
    mundo.esp1.post(f"{API}/historial/{esp[-1]['id']}/revertir")
    despues = mundo.aux.get(f"{API}/citas/{c}").json()["historial"]
    assert not any(h["reversible"] for h in despues)


def test_specialist_cannot_revert_a_cancellation_but_the_auxiliar_can(mundo, conn):
    from .test_api import motivo_id
    c = book(conn, mundo.p1, mundo.pro1, at(2, "09:00"))
    conn.commit()
    mundo.aux.post(f"{API}/citas/{c}/cancelar", json={"motivo_id": motivo_id(conn)})
    assert mundo.esp1.get(f"{API}/citas/{c}").json()["historial"][-1]["reversible"] is False
    assert mundo.aux.get(f"{API}/citas/{c}").json()["historial"][-1]["reversible"] is True
    ficha = mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()
    assert [h["reversible"] for h in ficha["historial"] if h["cita_id"] == c][0] is True


def test_el_paquete_no_importa_streamlit_ni_plotly():
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parents[1]
    patron = re.compile(r"^\s*(import|from)\s+(streamlit|plotly)\b", re.M)
    ofensores = [str(p) for p in (raiz / "estudia").rglob("*.py") if patron.search(p.read_text())]
    assert ofensores == []
    assert "streamlit" not in (raiz / "Makefile").read_text().lower()
    assert "streamlit" not in (raiz / "pyproject.toml").read_text().lower()
