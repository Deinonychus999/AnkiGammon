# OGXM v2 support: reader notes

AnkiGammon reads OGXM v2, HedgeHog's binary match-and-analysis format. It needs the format for two things: importing `.ogxm` files directly, and reading the analysis file HedgeHog's partner API returns (`GET /api/v1/analysis/<id>/ogxm`). HedgeHog serves that analysis only in binary; it declined a JSON variant on purpose.

**Normative spec:** `docs/OGXM_FORMAT_SPEC.md` in gitlab.com/eranlambooij/hedgehog-public (MIT). Where the spec and HedgeHog's C++ disagree, the C++ is what HedgeHog's own files follow.

## Modules

| Module | Job |
|---|---|
| `ankigammon/utils/ogxm_reader.py` | Container, record framing, MTCH/GAME/ply stream, replay, first ANAL + DECS |
| `ankigammon/utils/hedgehog_met.py` | HedgeHog's Rockwell-Kazaross MET and the match cube normalization |
| `ankigammon/parsers/ogxm_parser.py` | Decoded match → `List[Decision]`, plus player names for the import dialog |

Pure stdlib and Qt-free, so the browser version can use them later. **OGXM v1 files are refused** with a message, not converted.

## Traps (all covered by tests)

1. **Perspective.** Boards are absolute (White positive, bar at 0, moving up). `Position` is from the view of the player on roll, so flip when White (X) is on roll.
2. **Two step encodings.** Ply steps are zero-terminated within `move_bytes`. Alternative steps are count-prefixed.
3. **`ply_ref`** counts every ply across all games, markers and cube plies included. HedgeHog's per-game `ply_num` is the same index local to its game.
4. **Cube records sit on different plies:**
   - on a dice ply: the doubler's decision before the roll
   - on a double ply: the doubler's decision
   - on a take/drop ply: the responder's decision
   AnkiGammon merges a double with its answer into one cube Decision: `cube_error` comes from the doubler, `take_error` from the responder.
5. **Mixed perspectives in response records.** The cube triple is always the doubler's, but `probs` and `equity_loss` are the record seat's.
6. **Match units.** In match play, checker equities are normalized (EMG) and cube equities are raw MWC. Normalize the triple with HedgeHog's own MET, not the bundled Kazaross XG2: with XG2 the pass-anchor check fails and the numbers drift from HedgeHog's.
7. **`currency` can't be trusted.** It reads "money" on HedgeHog's match analyses, so key off `match_length`.
8. **Crawford is derived, not stored:** the first game that starts with either side one point away, if the rules have the Crawford bit.
9. **`alternatives[0]` is the best move by definition.** Never sort alternatives by equity; `is_played` marks the played move.

## Fixtures

`tests/data/hedgehog/` holds HedgeHog's 2ply analysis of `match_files/rchoicebug.mat`, the positions HedgeHog replayed for every ply, its blunder rows, and live position-analysis answers.
