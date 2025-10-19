# Interactive MCQ Feature - Implementation Plan (REVISED)

## Overview

Add interactive quiz functionality where users can click on multiple choice options **on the card front** to **flip to the card back**, which then shows whether their answer was correct. This creates a more engaging learning experience while maintaining full compatibility with Anki's card structure.

**Key Design**: Similar to interactive moves, but on the FRONT side. When a user clicks an option, Anki flips to the back, and the back dynamically highlights whether the clicked answer was correct or incorrect.

## User's Requirement Analysis

> "I would like to have a similar sort of interactivity as the result move visualization, but for the optional multiple choices. when the user clicks a choice, it reveals the back of the card and the back of the card shows whether or not the user got it."

### Key Insights

1. **Similar to interactive moves**: Use same patterns (JavaScript IIFE, data attributes, CSS state classes)
2. **Click triggers flip**: Unlike interactive moves (which stay on back), MCQ clicks flip from front to back
3. **Back shows correctness**: The card back must know which option was clicked and display feedback

## Current State Analysis

### Existing MCQ Implementation

- **Display**: Static text options (A-E) shown on card front when `show_options=True`
- **Answer Reveal**: Traditional Anki flip shows correct answer letter and move notation on back
- **Interactivity**: None - user reads options, mentally chooses, then flips
- **Shuffling**: Candidates randomly shuffled, answer index tracked

### Key Files

- [xg2anki/anki/card_generator.py](xg2anki/anki/card_generator.py) - Card HTML generation
- [xg2anki/anki/card_styles.py](xg2anki/anki/card_styles.py) - CSS styling
- [xg2anki/settings.py](xg2anki/settings.py) - User preferences

## Architecture: Front-Side Interactivity with Back-Side Feedback

### How Anki Card Flipping Works

Anki provides JavaScript APIs for card flipping:
- **Desktop/AnkiWeb**: `pycmd('ans')` triggers flip to back
- **Mobile (AnkiDroid/AnkiMobile)**: Different implementations but support custom JavaScript

### Data Flow

```
User sees front with clickable options (A-E)
    ↓
User clicks option C
    ↓
JavaScript stores choice in sessionStorage/hidden input
    ↓
JavaScript triggers Anki flip: pycmd('ans')
    ↓
Card back loads
    ↓
Back-side JavaScript reads stored choice
    ↓
Compares to correct answer
    ↓
Shows green checkmark (correct) or red X + correct answer (incorrect)
```

### Key Technical Challenge: Passing Data from Front to Back

**Problem**: How to pass the user's selected option from front side to back side?

**Solutions**:

1. **Session Storage** (RECOMMENDED)
   - Store selected option in `sessionStorage`
   - Back-side JavaScript reads from storage
   - Pros: Clean, works across sides, no DOM pollution
   - Cons: Requires session storage support (all modern Anki versions have it)

2. **URL Hash Fragment**
   - Set `window.location.hash = '#option-C'`
   - Back reads from `window.location.hash`
   - Pros: Works everywhere, survives navigation
   - Cons: Visible in URL bar (minor cosmetic issue)

3. **Hidden Input Field**
   - Add `<input type="hidden" id="user-choice">` to front
   - Anki preserves hidden inputs across flip
   - Pros: Simple, no storage needed
   - Cons: May not work on all Anki platforms

**DECISION**: Use Session Storage with Hash Fragment fallback for maximum compatibility.

## Proposed Feature: Interactive MCQ

### User Experience Flow

1. **Initial State (Front)**:
   - User sees board position + question + clickable options (A-E)
   - Options have hover effect to indicate clickability

2. **User Clicks Option** (e.g., C):
   - Option briefly highlights (visual feedback)
   - JavaScript stores choice: `sessionStorage.setItem('mcq-choice', 'C')`
   - JavaScript triggers flip: `pycmd('ans')`
   - Card flips to back

3. **Card Back Loads**:
   - JavaScript reads: `sessionStorage.getItem('mcq-choice')` → 'C'
   - Compares to correct answer (encoded in data attribute)
   - **If correct**:
     - Shows green checkmark: "✓ Correct! You selected C"
     - Option C in analysis table is highlighted green
   - **If incorrect**:
     - Shows red X: "✗ Incorrect. You selected C, but the correct answer is A"
     - Option C is highlighted red, correct option A is highlighted green

4. **Analysis Table**:
   - Standard analysis table shows all moves (as currently)
   - Selected option and correct option are visually distinguished

5. **Traditional Flip Still Works**:
   - If user doesn't click an option but manually flips (spacebar/click), back shows neutral state
   - "No answer selected - Here's the correct answer: A"

## Implementation Plan

### Phase 1: Settings & Configuration

**File**: [xg2anki/settings.py](xg2anki/settings.py)

#### 1.1 Add Setting

```python
DEFAULT_SETTINGS = {
    # ... existing settings ...
    "interactive_mcq": False,  # New setting (default OFF)
}

@property
def interactive_mcq(self) -> bool:
    """Get whether to enable interactive MCQ quiz mode."""
    return self._settings.get("interactive_mcq", False)

@interactive_mcq.setter
def interactive_mcq(self, value: bool) -> None:
    """Set whether to enable interactive MCQ quiz mode."""
    self.set("interactive_mcq", value)
```

**Why OFF by default**: Optional feature like `interactive_moves`, users opt-in.

---

### Phase 2: Card Generator Updates

**File**: [xg2anki/anki/card_generator.py](xg2anki/anki/card_generator.py)

#### 2.1 Constructor

Add `interactive_mcq` parameter (line ~28):

```python
def __init__(
    self,
    output_dir: Path,
    show_options: bool = False,
    interactive_moves: bool = False,
    interactive_mcq: bool = False,  # NEW
    renderer: Optional[BoardRenderer] = None
):
    self.interactive_mcq = interactive_mcq
```

#### 2.2 Front Generation Logic

Modify `_generate_text_mcq_front()` to be conditional (line ~188):

```python
def _generate_text_mcq_front(
    self,
    decision: Decision,
    position_image: str,
    candidates: List[Optional[Move]]
) -> str:
    """Generate HTML for text-based MCQ front."""

    if self.interactive_mcq:
        return self._generate_interactive_mcq_front(
            decision, position_image, candidates
        )
    else:
        # EXISTING static MCQ front code (lines 195-220)
        return self._generate_static_mcq_front(
            decision, position_image, candidates
        )
```

#### 2.3 Extract Static MCQ Front (Refactor)

Create new method `_generate_static_mcq_front()` with existing logic (lines 195-220):

```python
def _generate_static_mcq_front(
    self,
    decision: Decision,
    position_image: str,
    candidates: List[Optional[Move]]
) -> str:
    """Generate HTML for static (non-interactive) MCQ front."""
    metadata = self._get_metadata_html(decision)

    # Format candidate options
    options_html = []
    letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    for i, candidate in enumerate(candidates):
        if candidate:
            options_html.append(
                f"<div class='option'><strong>{letters[i]}.</strong> {candidate.notation}</div>"
            )

    html = f"""
<div class="card-front">
    <div class="position-image">
        <img src="{Path(position_image).name}" alt="Position" />
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>What is the best move?</h3>
        <div class="options">
            {''.join(options_html)}
        </div>
    </div>
</div>
"""
    return html
```

#### 2.4 New Interactive MCQ Front

Create new method `_generate_interactive_mcq_front()`:

```python
def _generate_interactive_mcq_front(
    self,
    decision: Decision,
    position_image: str,
    candidates: List[Optional[Move]]
) -> str:
    """Generate interactive quiz MCQ front with clickable options."""

    metadata = self._get_metadata_html(decision)
    letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

    # Build clickable options with data attributes
    options_html = []
    for i, candidate in enumerate(candidates):
        if candidate:
            options_html.append(f"""
<div class='mcq-option' data-option-letter='{letters[i]}'>
    <strong>{letters[i]}.</strong> {candidate.notation}
</div>
""")

    html = f"""
<div class="card-front interactive-mcq-front">
    <div class="position-image">
        <img src="{Path(position_image).name}" alt="Position" />
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>What is the best move?</h3>
        <div class="mcq-options">
            {''.join(options_html)}
        </div>
        <p class="mcq-hint">Click an option to see if you're correct</p>
    </div>
</div>

<script>
{self._generate_mcq_front_javascript()}
</script>
"""
    return html
```

#### 2.5 Front-Side JavaScript

Create new method `_generate_mcq_front_javascript()`:

```python
def _generate_mcq_front_javascript(self) -> str:
    """Generate JavaScript for interactive MCQ front side."""
    return """
(function() {
    const options = document.querySelectorAll('.mcq-option');

    options.forEach(option => {
        option.addEventListener('click', function() {
            const selectedLetter = this.dataset.optionLetter;

            // Store selection in sessionStorage (primary method)
            try {
                sessionStorage.setItem('xg2anki-mcq-choice', selectedLetter);
            } catch (e) {
                // Fallback: use URL hash
                window.location.hash = 'choice-' + selectedLetter;
            }

            // Visual feedback before flip
            this.classList.add('selected-flash');

            // Trigger Anki flip to back side
            setTimeout(function() {
                if (typeof pycmd !== 'undefined') {
                    pycmd('ans');  // Anki desktop
                } else if (typeof AnkiDroidJS !== 'undefined') {
                    AnkiDroidJS.ankiShowAnswer();  // AnkiDroid
                } else {
                    // Fallback: simulate spacebar press (works on AnkiMobile)
                    const event = new KeyboardEvent('keydown', { keyCode: 32 });
                    document.dispatchEvent(event);
                }
            }, 200);  // 200ms delay for visual feedback
        });
    });
})();
"""
```

#### 2.6 Back Generation Updates

Modify `_generate_back()` to handle interactive MCQ (around line 222):

**Key changes**:
1. Add `data-correct-answer` attribute to card back
2. Conditionally add feedback section
3. Add back-side JavaScript if `interactive_mcq` is enabled

```python
def _generate_back(
    self,
    decision: Decision,
    original_position_image: str,
    result_position_image: str,
    candidates: List[Optional[Move]],
    answer_index: int,
    show_options: bool,
    move_result_images: Dict[str, str]
) -> str:
    """Generate HTML for card back."""
    metadata = self._get_metadata_html(decision)

    # ... existing table generation code (lines 236-276) ...

    # Generate answer section
    best_move = decision.get_best_move()
    best_notation = best_move.notation if best_move else "Unknown"
    letters = ['A', 'B', 'C', 'D', 'E']
    correct_letter = letters[answer_index] if answer_index < len(letters) else "?"

    # Conditional answer section based on interactive_mcq
    if show_options and self.interactive_mcq:
        # Interactive MCQ: Add feedback section + standard answer
        answer_html = f"""
    <div class="mcq-feedback-container" id="mcq-feedback" style="display: none;">
        <!-- Populated by JavaScript based on user's choice -->
    </div>
    <div class="answer" data-correct-answer="{correct_letter}">
        <h3>Correct Answer: <span class="answer-letter">{correct_letter}</span></h3>
        <p class="best-move-notation">{best_notation}</p>
    </div>
"""
    elif show_options:
        # Static MCQ: Standard answer display
        answer_html = f"""
    <div class="answer">
        <h3>Correct Answer: <span class="answer-letter">{correct_letter}</span></h3>
        <p class="best-move-notation">{best_notation}</p>
    </div>
"""
    else:
        # Non-MCQ: Simple answer
        answer_html = f"""
    <div class="answer">
        <h3>Best Move:</h3>
        <p class="best-move-notation">{best_notation}</p>
    </div>
"""

    # ... rest of existing back generation code ...

    # Add interactive MCQ JavaScript if enabled
    if show_options and self.interactive_mcq:
        html += self._generate_mcq_back_javascript(correct_letter)

    # Add interactive moves JavaScript if enabled (existing code, line 353)
    if self.interactive_moves:
        html += """..."""  # existing interactive moves JS

    return html
```

#### 2.7 Back-Side JavaScript

Create new method `_generate_mcq_back_javascript()`:

```python
def _generate_mcq_back_javascript(self, correct_letter: str) -> str:
    """Generate JavaScript for interactive MCQ back side."""
    return f"""
<script>
(function() {{
    // Get user's selected answer from storage
    let selectedLetter = null;

    // Try sessionStorage first
    try {{
        selectedLetter = sessionStorage.getItem('xg2anki-mcq-choice');
        // Clear after reading to avoid persisting across cards
        sessionStorage.removeItem('xg2anki-mcq-choice');
    }} catch (e) {{
        // Fallback: read from URL hash
        const hash = window.location.hash;
        if (hash.startsWith('#choice-')) {{
            selectedLetter = hash.replace('#choice-', '');
            // Clear hash
            window.location.hash = '';
        }}
    }}

    const correctLetter = '{correct_letter}';
    const feedbackContainer = document.getElementById('mcq-feedback');

    if (selectedLetter) {{
        feedbackContainer.style.display = 'block';

        if (selectedLetter === correctLetter) {{
            // Correct answer
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-correct">
                    <div class="feedback-icon">✓</div>
                    <div class="feedback-text">
                        <strong>Correct!</strong> You selected <strong>${{selectedLetter}}</strong>
                    </div>
                </div>
            `;
        }} else {{
            // Incorrect answer
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-incorrect">
                    <div class="feedback-icon">✗</div>
                    <div class="feedback-text">
                        <strong>Incorrect.</strong> You selected <strong>${{selectedLetter}}</strong>,
                        but the correct answer is <strong>${{correctLetter}}</strong>
                    </div>
                </div>
            `;
        }}
    }} else {{
        // No selection (user flipped manually without clicking)
        feedbackContainer.style.display = 'block';
        feedbackContainer.innerHTML = `
            <div class="mcq-feedback-neutral">
                <div class="feedback-text">
                    No answer selected. The correct answer is <strong>${{correctLetter}}</strong>
                </div>
            </div>
        `;
    }}
}})();
</script>
"""
```

---

### Phase 3: CSS Styling

**File**: [xg2anki/anki/card_styles.py](xg2anki/anki/card_styles.py)

Add styles after the interactive moves section (after line ~279):

```css
/* ===================================================================
   INTERACTIVE MCQ STYLES
   =================================================================== */

/* Front Side: Clickable Options */
.mcq-option {
    cursor: pointer;
    padding: 12px 16px;
    margin: 10px 0;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 6px;
    font-size: 16px;
    transition: all 0.2s ease;
    user-select: none;  /* Prevent text selection on click */
}

.mcq-option:hover {
    background-color: rgba(100, 150, 255, 0.1);
    border-color: #4da6ff;
    transform: translateX(4px);
}

.mcq-option.selected-flash {
    background-color: rgba(100, 150, 255, 0.3);
    border-color: #4da6ff;
    border-width: 3px;
}

/* Hint text below options */
.mcq-hint {
    margin-top: 20px;
    font-size: 13px;
    color: #999;
    font-style: italic;
    text-align: center;
}

/* Back Side: Feedback Messages */
.mcq-feedback-container {
    margin: 20px 0;
    padding: 20px;
    border-radius: 8px;
    font-size: 16px;
}

.mcq-feedback-correct,
.mcq-feedback-incorrect,
.mcq-feedback-neutral {
    display: flex;
    align-items: center;
    gap: 15px;
}

.feedback-icon {
    font-size: 40px;
    font-weight: bold;
    flex-shrink: 0;
}

.feedback-text {
    flex-grow: 1;
}

/* Correct feedback (green) */
.mcq-feedback-correct {
    background-color: rgba(76, 175, 80, 0.15);
    border: 2px solid #4caf50;
}

.mcq-feedback-correct .feedback-icon {
    color: #4caf50;
}

.mcq-feedback-correct .feedback-text {
    color: #2e7d32;
}

/* Incorrect feedback (red) */
.mcq-feedback-incorrect {
    background-color: rgba(244, 67, 54, 0.15);
    border: 2px solid #f44336;
}

.mcq-feedback-incorrect .feedback-icon {
    color: #f44336;
}

.mcq-feedback-incorrect .feedback-text {
    color: #c62828;
}

/* Neutral feedback (no selection) */
.mcq-feedback-neutral {
    background-color: rgba(158, 158, 158, 0.1);
    border: 2px solid #9e9e9e;
    padding: 15px;
}

.mcq-feedback-neutral .feedback-text {
    color: var(--text-fg);
}

/* Dark mode adjustments */
.night_mode .mcq-feedback-correct {
    background-color: rgba(76, 175, 80, 0.25);
}

.night_mode .mcq-feedback-incorrect {
    background-color: rgba(244, 67, 54, 0.25);
}

.night_mode .mcq-feedback-neutral {
    background-color: rgba(158, 158, 158, 0.2);
}
```

---

### Phase 4: CLI & Interactive Mode Integration

#### 4.1 CLI Argument

**File**: [xg2anki/cli.py](xg2anki/cli.py)

Add flag after `--interactive-moves` (around line 54):

```python
@click.option(
    '--interactive-mcq',
    is_flag=True,
    help='Enable interactive MCQ quiz mode (clickable options with instant feedback)'
)
def main(..., interactive_moves, interactive_mcq, ...):
    # Pass to exporters
```

#### 4.2 Export Function Updates

Update function signatures (lines ~144, ~170):

```python
def export_apkg(decisions, output_dir, deck_name, show_options, color_scheme="classic",
                interactive_moves=False, interactive_mcq=False):
    exporter = ApkgExporter(output_dir, deck_name)
    output_file = exporter.export(
        decisions,
        output_file="xg_deck.apkg",
        show_options=show_options,
        color_scheme=color_scheme,
        interactive_moves=interactive_moves,
        interactive_mcq=interactive_mcq  # NEW
    )

def export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme="classic",
                       interactive_moves=False, interactive_mcq=False):
    client = AnkiConnect(deck_name=deck_name)
    results = client.export_decisions(
        decisions,
        output_dir=output_dir,
        show_options=show_options,
        color_scheme=color_scheme,
        interactive_moves=interactive_moves,
        interactive_mcq=interactive_mcq  # NEW
    )
```

#### 4.3 Interactive Mode Menu

**File**: [xg2anki/interactive.py](xg2anki/interactive.py)

Add menu option in `show_options_menu()` (around line 100):

```python
def show_options_menu(self):
    while True:
        click.echo(f"  1. Color scheme (current: {self.color_scheme})")
        click.echo(f"  2. Show move options (current: {'Yes' if self.settings.show_options else 'No'})")
        click.echo(f"  3. Antialiasing quality (current: {aa_display})")
        click.echo(f"  4. Interactive moves (current: {'Yes' if self.settings.interactive_moves else 'No'})")
        click.echo(f"  5. Interactive MCQ (current: {'Yes' if self.settings.interactive_mcq else 'No'})")  # NEW
        click.echo(f"  6. Back to main menu")  # Renumber

        choice = click.prompt(...)

        # ... existing handlers ...

        elif choice == '5':
            self.toggle_interactive_mcq()
        elif choice == '6':  # Was '5'
            break
```

Add toggle handler (around line 220):

```python
def toggle_interactive_mcq(self):
    """Toggle interactive MCQ quiz mode."""
    click.echo()
    click.echo(click.style("=" * 60, fg='cyan'))
    click.echo(click.style("  Interactive MCQ Quiz Mode", fg='cyan', bold=True))
    click.echo(click.style("=" * 60, fg='cyan'))
    click.echo()
    click.echo("When enabled, card fronts will have clickable multiple choice options:")
    click.echo("  - Click an option to flip the card and see if you're correct")
    click.echo("  - Card back shows green checkmark (correct) or red X (incorrect)")
    click.echo("  - Works alongside standard Anki review (spacebar still works)")
    click.echo()
    click.echo(click.style("Note:", fg='yellow'), nl=False)
    click.echo(" This requires 'Show move options' to be enabled.")
    click.echo("       If disabled, this setting will have no effect.")
    click.echo()

    new_value = click.confirm(
        click.style("Enable interactive MCQ quiz mode?", fg='green'),
        default=self.settings.interactive_mcq
    )

    self.settings.interactive_mcq = new_value  # Auto-saves

    click.echo()
    if new_value and not self.settings.show_options:
        click.echo(click.style("  Warning: Interactive MCQ is enabled, but 'Show move options' is OFF.", fg='yellow'))
        click.echo(click.style("           Cards will not show multiple choice options.", fg='yellow'))
        click.echo()
        if click.confirm("Would you like to enable 'Show move options' now?"):
            self.settings.show_options = True
            click.echo(click.style("  Both settings enabled!", fg='green'))
    else:
        click.echo(click.style(f"  Setting saved: {'Interactive MCQ enabled' if new_value else 'Interactive MCQ disabled'}", fg='green'))
    click.echo()
```

Update `export_deck()` to pass the parameter (around line 490):

```python
def export_deck(self, decisions: List[Decision], deck_name: str,
               output_format: str, show_options: bool, color_scheme: str = "classic",
               interactive_moves: bool = False, interactive_mcq: bool = False):
    # ...
    if output_format == 'apkg':
        export_apkg(decisions, output_dir, deck_name, show_options, color_scheme,
                   interactive_moves, interactive_mcq)
    elif output_format == 'ankiconnect':
        export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme,
                          interactive_moves, interactive_mcq)
```

---

### Phase 5: Exporter Updates

#### 5.1 AnkiConnect Exporter

**File**: [xg2anki/anki/ankiconnect.py](xg2anki/anki/ankiconnect.py)

Update `export_decisions()` method:

```python
def export_decisions(self, decisions, output_dir, show_options=False,
                    color_scheme="classic", interactive_moves=False, interactive_mcq=False):
    generator = CardGenerator(
        output_dir,
        show_options=show_options,
        interactive_moves=interactive_moves,
        interactive_mcq=interactive_mcq,  # NEW
        renderer=BoardRenderer(color_scheme=color_scheme)
    )
    # ... rest of method
```

#### 5.2 APKG Exporter

**File**: [xg2anki/anki/apkg_exporter.py](xg2anki/anki/apkg_exporter.py)

Update `export()` method:

```python
def export(self, decisions, output_file="xg_deck.apkg", show_options=False,
          color_scheme="classic", interactive_moves=False, interactive_mcq=False):
    generator = CardGenerator(
        self.output_dir,
        show_options=show_options,
        interactive_moves=interactive_moves,
        interactive_mcq=interactive_mcq,  # NEW
        renderer=BoardRenderer(color_scheme=color_scheme)
    )
    # ... rest of method
```

---

## Edge Cases & Considerations

### 1. Compatibility with Interactive Moves

- **Question**: Can both features be enabled simultaneously?
- **Answer**: Yes, they're independent
  - `interactive_mcq`: Front-side option clicking
  - `interactive_moves`: Back-side move visualization
  - Both can coexist on the same card

### 2. Show Options Dependency

- **Issue**: `interactive_mcq` is meaningless if `show_options=False`
- **Mitigation**:
  - Interactive mode warns user and offers to enable both
  - CLI documentation clarifies dependency
  - If `interactive_mcq=True` but `show_options=False`, card front is non-MCQ (graceful degradation)

### 3. Mobile Compatibility

**AnkiDroid**:
- Supports `sessionStorage`
- Has custom `AnkiDroidJS.ankiShowAnswer()` API (handled in JS)

**AnkiMobile**:
- Supports `sessionStorage`
- Simulates spacebar press as fallback

**Testing Strategy**:
- Test on Anki Desktop (Windows/Mac/Linux)
- Test on AnkiDroid
- Test on AnkiMobile (if available)
- Fallback: URL hash method works everywhere

### 4. Session Storage Persistence

- **Issue**: `sessionStorage` persists during the entire Anki session
- **Mitigation**: Clear after reading (`sessionStorage.removeItem()`) to avoid cross-card contamination

### 5. Manual Flip Behavior

- **Scenario**: User doesn't click an option but manually flips (spacebar/click "Show Answer")
- **Behavior**: Back shows neutral feedback: "No answer selected. The correct answer is A"
- **Why**: Preserves traditional Anki workflow, allows users to opt out of interaction

### 6. Spoiler Protection

- **Issue**: Correct answer is NOT visible on the front (unlike the original plan)
- **Advantage**: No spoiler risk; answer is only revealed on the back
- **Comparison**: This is BETTER than the original plan which had `data-is-correct` on front

### 7. Review Mode

- **Learning Mode**: Interactive MCQ works great (immediate feedback)
- **Review Mode**: Also works (refresher on correctness)
- **Cramming**: Works (quick practice)

---

## Testing Strategy

### 1. Unit Tests

**File**: Create `tests/test_interactive_mcq.py`

```python
def test_interactive_mcq_front_generation():
    """Test that interactive MCQ front has clickable options."""
    generator = CardGenerator(output_dir, show_options=True, interactive_mcq=True)
    card = generator.generate_card(decision)

    assert 'mcq-option' in card['front']
    assert 'data-option-letter' in card['front']
    assert 'sessionStorage' in card['front']
    assert 'pycmd' in card['front']

def test_interactive_mcq_back_feedback():
    """Test that back has feedback section."""
    generator = CardGenerator(output_dir, show_options=True, interactive_mcq=True)
    card = generator.generate_card(decision)

    assert 'mcq-feedback' in card['back']
    assert 'data-correct-answer' in card['back']
    assert 'sessionStorage.getItem' in card['back']

def test_interactive_mcq_disabled_fallback():
    """Test that disabling interactive_mcq shows static MCQ."""
    generator = CardGenerator(output_dir, show_options=True, interactive_mcq=False)
    card = generator.generate_card(decision)

    assert 'mcq-option' not in card['front']  # No clickable options
    assert 'class="option"' in card['front']  # Static options
    assert 'sessionStorage' not in card['front']
```

### 2. Integration Tests

```python
def test_both_interactive_features_enabled():
    """Test that interactive_mcq and interactive_moves work together."""
    generator = CardGenerator(output_dir, show_options=True,
                             interactive_mcq=True, interactive_moves=True)
    card = generator.generate_card(decision)

    assert 'mcq-option' in card['front']  # MCQ on front
    assert 'move-row' in card['back']  # Interactive moves on back
    assert card['front'].count('<script>') == 1  # Front JS
    assert card['back'].count('<script>') == 2  # Back JS (MCQ + moves)
```

### 3. Manual Testing Checklist

- [ ] **Desktop (Windows)**:
  - [ ] Click option A (correct) → flip → green checkmark
  - [ ] Click option C (incorrect) → flip → red X + correct answer shown
  - [ ] Don't click, press spacebar → flip → neutral "no answer selected"

- [ ] **Desktop (Mac/Linux)**: Same as Windows

- [ ] **AnkiDroid**:
  - [ ] Click option → flip works
  - [ ] Feedback displays correctly
  - [ ] sessionStorage works

- [ ] **AnkiMobile** (if available):
  - [ ] Click option → flip works
  - [ ] Fallback mechanism works if sessionStorage fails

- [ ] **Dark Mode**:
  - [ ] Feedback colors readable in dark theme
  - [ ] Option hover states visible

- [ ] **Edge Cases**:
  - [ ] Cube decisions (5 options)
  - [ ] Checker play (2-5 options)
  - [ ] Both interactive_mcq and interactive_moves enabled
  - [ ] interactive_mcq=True but show_options=False (should show non-MCQ front)

---

## Migration Path

### Default Behavior

- `interactive_mcq = False` (off by default, like `interactive_moves`)
- Existing users: No change
- New users: Can opt-in via settings or CLI flag

### Documentation Updates

**File**: [CLAUDE.md](CLAUDE.md)

Add to "Settings Persistence" section:

```markdown
- `interactive_mcq` - Enable interactive MCQ quiz mode (default: false)
  - When enabled, card fronts have clickable options that trigger flip to back
  - Back shows whether the selected answer was correct (green) or incorrect (red)
  - Requires `show_options=true` to have any effect
```

Add to "Architecture" section:

```markdown
#### Interactive MCQ Architecture

The interactive MCQ feature adds front-side interactivity:

1. **Front Side**: Clickable options (A-E) with JavaScript event handlers
2. **Click Handler**: Stores selection in sessionStorage, triggers Anki flip
3. **Back Side**: Reads selection, compares to correct answer, displays feedback
4. **Feedback States**: Correct (green), Incorrect (red), Neutral (no selection)
5. **Compatibility**: Works on Anki desktop, AnkiDroid, AnkiMobile

**Data Flow**:
```
Front: User clicks option → sessionStorage.setItem() → pycmd('ans')
  ↓ (Anki flips card)
Back: sessionStorage.getItem() → compare → show feedback
```

**Comparison to Interactive Moves**:
- Interactive Moves: Back-side only, image switching
- Interactive MCQ: Front-to-back, answer validation
```

---

## Open Questions (RESOLVED)

### ✓ 1. Approach: Front-only vs Single-sided?

**ANSWER**: Front-to-back approach (stores choice, flips, validates on back)
- Maintains Anki's card model (front/back still exists)
- Answer NOT visible on front (better than original plan)
- JavaScript on both sides (front for click, back for validation)

### ✓ 2. How to pass data from front to back?

**ANSWER**: sessionStorage + URL hash fallback
- Primary: `sessionStorage.setItem('xg2anki-mcq-choice', letter)`
- Fallback: `window.location.hash = '#choice-' + letter`
- Clear after reading to avoid cross-card contamination

### ✓ 3. What if user doesn't click an option?

**ANSWER**: Neutral feedback state
- Back detects no stored choice
- Shows: "No answer selected. The correct answer is A"
- Allows traditional Anki workflow to coexist

### ✓ 4. Button labels or auto-flip?

**ANSWER**: Auto-flip on click (no buttons needed)
- Cleaner UX (fewer clicks)
- Matches user's request: "click a choice, it reveals the back"

### ✓ 5. Sound effects?

**ANSWER**: No custom sounds (rely on Anki's defaults)
- Anki already plays sounds on answer reveal
- Custom sounds require audio files (adds complexity)

### ✓ 6. Timing tracking?

**ANSWER**: Not in v1 (can add later)
- Requires more complex JavaScript (timers, state management)
- Would need storage for per-card timing data
- Future enhancement: track time, show "Answered in 3.2 seconds"

---

## Success Criteria

- [x] **Architecture designed**: Front-to-back with sessionStorage
- [ ] Users can click options on front to flip card
- [ ] Back shows correct/incorrect feedback with visual distinction
- [ ] Neutral feedback when user flips manually
- [ ] Traditional card flip still works (spacebar/click)
- [ ] Settings persist across sessions
- [ ] Works in Anki desktop (Windows/Mac/Linux)
- [ ] Works in AnkiDroid
- [ ] Works in AnkiMobile (best effort)
- [ ] No performance degradation
- [ ] Code follows existing patterns (IIFE, data attributes, CSS classes)
- [ ] Code is maintainable and well-documented

---

## Estimated Complexity

**Time**: 4-5 hours implementation + 2-3 hours testing

**Breakdown**:
- Phase 1 (Settings): 20 minutes
- Phase 2 (Card Generator): 2 hours (front HTML/JS, back HTML/JS)
- Phase 3 (CSS): 30 minutes
- Phase 4 (CLI/Interactive): 1 hour
- Phase 5 (Exporters): 30 minutes
- Testing: 2-3 hours (unit tests + manual cross-platform)

**Dependencies**: None (self-contained feature)

**Risk Level**: Low-Medium
- **Risks**: JavaScript compatibility (AnkiMobile), sessionStorage support
- **Mitigation**: Fallback mechanisms, graceful degradation, thorough testing

---

## Comparison to Original Plan

### What Changed

| Aspect | Original Plan | Revised Plan |
|--------|---------------|--------------|
| **Architecture** | Front-side only (all on front) | Front-to-back (click front, validate back) |
| **Answer Reveal** | JavaScript shows/hides on front | Anki flips to back |
| **Data Passing** | Not needed (all on front) | sessionStorage + hash fallback |
| **Spoiler Risk** | HIGH (answer in front HTML) | NONE (answer only on back) |
| **Anki Compatibility** | Breaks traditional flip model | Preserves traditional flip |
| **User Flow** | Click → instant feedback on front | Click → flip → feedback on back |
| **Complexity** | Medium | Medium (same) |

### Why This Is Better

1. **No Spoiler Risk**: Answer is never encoded on the front side
2. **Anki Native**: Uses Anki's built-in flip mechanism (feels natural)
3. **Traditional Fallback**: Spacebar flip still works (no forced interaction)
4. **Mental Model**: Matches user's request ("reveals the back")
5. **Mobile Compatible**: Leverages Anki's cross-platform flip APIs
6. **Consistent**: Matches interactive moves pattern (JavaScript on both sides)

---

## Next Steps (Implementation Order)

1. **Phase 1**: Add setting to `settings.py` ✓
2. **Phase 2**: Implement card generator changes (front + back) ✓
3. **Phase 3**: Add CSS styles ✓
4. **Phase 4**: CLI and interactive mode integration ✓
5. **Phase 5**: Update exporters ✓
6. **Testing**: Unit tests, integration tests, manual testing
7. **Documentation**: Update CLAUDE.md and README

---

**Status**: READY FOR IMPLEMENTATION

**Reviewer**: Please validate this approach before coding begins.
