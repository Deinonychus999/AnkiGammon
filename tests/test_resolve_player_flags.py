"""Unit tests for MainWindow._resolve_player_flags name-matching logic.

The function maps a file's two player names against a cached selection,
returning (include_player_x, include_player_o). XG/match files use
player1 = internal Player.O, player2 = Player.X, so the returned tuple
order is intentionally swapped relative to the input arguments.
"""

from ankigammon.gui.main_window import MainWindow


resolve = MainWindow._resolve_player_flags


class TestResolvePlayerFlags:
    def test_slot1_match(self):
        # player1 ("Frank") matches → include_player_o True
        assert resolve("Frank", "Bob", ["Frank"]) == (False, True)

    def test_slot2_match(self):
        # player2 ("Frank") matches → include_player_x True
        assert resolve("Bob", "Frank", ["Frank"]) == (True, False)

    def test_both_match(self):
        assert resolve("Frank", "Bob", ["Frank", "Bob"]) == (True, True)

    def test_neither_match(self):
        assert resolve("Carol", "Dave", ["Frank", "Bob"]) == (False, False)

    def test_case_insensitive(self):
        assert resolve("FRANK", "bob", ["frank", "BOB"]) == (True, True)

    def test_strips_whitespace(self):
        # Trailing/leading whitespace must not break the match
        assert resolve("Frank ", " Bob", ["Frank", "Bob"]) == (True, True)
        assert resolve("Frank", "Bob", [" Frank ", "Bob "]) == (True, True)

    def test_none_player_names(self):
        # extract_player_names can return (None, None) on a malformed header
        assert resolve(None, None, ["Frank"]) == (False, False)
        assert resolve(None, "Frank", ["Frank"]) == (True, False)
        assert resolve("Frank", None, ["Frank"]) == (False, True)

    def test_empty_selected_names(self):
        # Sentinel used when the batch dialog can't be shown
        assert resolve("Frank", "Bob", []) == (False, False)

    def test_empty_string_player_names(self):
        # Empty strings should not match anything, even an empty selected name
        assert resolve("", "", ["Frank"]) == (False, False)

    def test_slot_independence(self):
        # Same name in either slot must produce a True flag for that slot only
        assert resolve("Frank", "Bob", ["Frank"]) == (False, True)
        assert resolve("Bob", "Frank", ["Frank"]) == (True, False)
