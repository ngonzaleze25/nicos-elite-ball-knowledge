from app import create_app


def test_home_page_loads_spanish_landing():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Nico's Elite Ball Knowledge" in page
    assert "LaLiga 2026-27" in page
    assert "la aplicación se ha iniciado correctamente" in page
