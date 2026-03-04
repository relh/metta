import pytest
from colorama import Fore, Style

from metta.common.util.text_styles import blue, bold, colorize, cyan, green, red, use_colors, yellow


class TestColoramaUtils:
    def setup_method(self):
        use_colors(True)

    def test_colorize_with_colors_enabled(self):
        text = "test text"
        color = Fore.RED
        expected = f"{color}{text}{Style.RESET_ALL}"
        assert colorize(text, color) == expected

    def test_colorize_with_colors_disabled(self):
        use_colors(False)
        text = "test text"
        assert colorize(text, Fore.RED) == text

    @pytest.mark.parametrize(
        ("func", "style", "text"),
        [
            (red, Fore.RED, "error message"),
            (green, Fore.GREEN, "success message"),
            (yellow, Fore.YELLOW, "warning message"),
            (cyan, Fore.CYAN, "info message"),
            (blue, Fore.BLUE, "blue message"),
            (bold, Style.BRIGHT, "bold message"),
        ],
        ids=["red", "green", "yellow", "cyan", "blue", "bold"],
    )
    def test_color_functions_apply_style(self, func, style, text):
        assert func(text) == f"{style}{text}{Style.RESET_ALL}"

    def test_use_colors_true(self):
        use_colors(True)
        assert red("test") == f"{Fore.RED}test{Style.RESET_ALL}"

    def test_use_colors_false(self):
        use_colors(False)
        assert red("test") == "test"

    def test_color_functions_with_empty_string(self):
        assert red("") == f"{Fore.RED}{Style.RESET_ALL}"
        assert green("") == f"{Fore.GREEN}{Style.RESET_ALL}"
        assert yellow("") == f"{Fore.YELLOW}{Style.RESET_ALL}"
        assert cyan("") == f"{Fore.CYAN}{Style.RESET_ALL}"
        assert blue("") == f"{Fore.BLUE}{Style.RESET_ALL}"
        assert bold("") == f"{Style.BRIGHT}{Style.RESET_ALL}"

    @pytest.mark.parametrize(
        ("func", "style", "text"),
        [
            (red, Fore.RED, "!@#$%^&*()_+-=[]{}|;':\",./<>?"),
            (green, Fore.GREEN, "Hello 世界 🌍"),
            (blue, Fore.BLUE, "Line 1\nLine 2\nLine 3"),
        ],
        ids=["special-chars", "unicode", "multiline"],
    )
    def test_color_functions_handle_text_variants(self, func, style, text):
        assert func(text) == f"{style}{text}{Style.RESET_ALL}"

    def test_color_functions_when_disabled(self):
        use_colors(False)
        text = "test message"

        assert red(text) == text
        assert green(text) == text
        assert yellow(text) == text
        assert cyan(text) == text
        assert blue(text) == text
        assert bold(text) == text

    def test_use_colors_toggle(self):
        use_colors(True)
        assert red("test") == f"{Fore.RED}test{Style.RESET_ALL}"

        use_colors(False)
        assert red("test") == "test"

        use_colors(True)
        assert red("test") == f"{Fore.RED}test{Style.RESET_ALL}"

    @pytest.mark.parametrize("style", [Fore.RED, Fore.GREEN, Style.BRIGHT, Style.DIM])
    def test_colorize_with_different_styles(self, style):
        text = "test"
        assert colorize(text, style) == f"{style}{text}{Style.RESET_ALL}"
