from recipes.experiment import game


def test_non_hunger_train_uses_default_steps_when_max_steps_omitted(monkeypatch) -> None:
    monkeypatch.setitem(game.GAMES, "fake", {})

    calls: list[int | None] = []
    original_make_game = game.make_game

    def fake_make_game(name: str, **kwargs):
        calls.append(kwargs.get("max_steps"))
        return original_make_game(
            "hunger",
            num_agents=kwargs.get("num_agents", 8),
            max_steps=kwargs.get("max_steps"),
            variants=kwargs.get("variants"),
        )

    monkeypatch.setattr(game, "make_game", fake_make_game)

    game.train(game="fake", num_agents=8, max_steps=None)

    assert calls
    assert calls[0] == 250
