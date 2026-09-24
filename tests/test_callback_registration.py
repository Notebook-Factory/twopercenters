"""Opening a panel must not register its callbacks again.

The compare tabs and the Explore section are built when a reader opens them,
and their builders declare @callback functions as they run. Dash reads its
list of callbacks once, before the first request, so every later build only
added copies that were never used and never freed, in every worker, on every
tab switch.
"""
from dash import _callback


def test_building_a_panel_after_startup_registers_nothing():
    import app
    from pages import home

    app.server.test_client().get("/")   # Dash reads its callbacks here
    before = (len(_callback.GLOBAL_CALLBACK_LIST),
              len(_callback.GLOBAL_INLINE_SCRIPTS))

    for _ in range(2):
        for tab in ("tab-1", "tab-2", "tab-3"):
            home.switch_tab(tab, "Ioannidis, John P.A.")
        home.build_explore("explore", "Ioannidis, John P.A.")

    after = (len(_callback.GLOBAL_CALLBACK_LIST),
             len(_callback.GLOBAL_INLINE_SCRIPTS))
    assert after == before


def test_every_panel_callback_is_registered_before_the_first_request():
    """The other half: skipping later registrations is only safe if the
    first one happened while Dash was still listening."""
    import app

    app.server.test_client().get("/")
    outputs = " ".join(app.app.callback_map)
    for component_id in ("author1OptionsDropdown_author_find_",
                         "selectYrRadioA1_author_find_",
                         "group2ListOptionsDropdown_author_vs_group"):
        assert component_id in outputs, component_id
