"""Shared card styling constants for Anki exports."""

# Model name for XG cards
MODEL_NAME = "XG Backgammon Decision"

# CSS for card styling with dark mode support
CARD_CSS = """
.card {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 16px;
    text-align: center;
    color: var(--text-fg);
    background-color: var(--canvas);
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
}

.position-svg svg,
.position-svg-container svg {
    max-width: 100%;
    height: auto;
    border: 2px solid var(--border);
    border-radius: 8px;
    margin: 10px 0;
    display: block;
}

.position-viewer {
    position: relative;
}

.position-svg-container {
    min-height: 200px;
}

.metadata {
    font-size: 14px;
    color: var(--text-fg);
    margin: 10px 0;
    padding: 10px;
    background-color: var(--canvas-elevated);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.question h3 {
    font-size: 20px;
    margin: 20px 0 10px;
    color: var(--text-fg);
}

.options {
    text-align: left;
    margin: 15px auto;
    max-width: 500px;
}

.option {
    padding: 10px;
    margin: 8px 0;
    background-color: var(--canvas-elevated);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 16px;
}

.option strong {
    color: #4da6ff;
    margin-right: 10px;
}

/* Image MCQ variant */
.option-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 15px;
    margin: 20px auto;
    max-width: 900px;
}

.option-image {
    position: relative;
    border: 2px solid var(--border);
    border-radius: 8px;
    padding: 5px;
    background-color: var(--canvas-elevated);
}

.option-image.empty {
    background-color: var(--canvas-inset);
    min-height: 200px;
}

.option-letter {
    position: absolute;
    top: 10px;
    left: 10px;
    background-color: #4da6ff;
    color: white;
    font-weight: bold;
    font-size: 18px;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
}

.option-image img {
    width: 100%;
    height: auto;
    border-radius: 4px;
}

.option-move {
    text-align: center;
    font-size: 14px;
    font-weight: bold;
    color: var(--text-fg);
    padding: 5px;
    margin-top: 5px;
    background-color: var(--canvas);
    border-radius: 4px;
}

/* Card back */
.answer {
    margin: 20px 0;
    padding: 15px;
    background-color: rgba(76, 175, 80, 0.15);
    border: 2px solid #4caf50;
    border-radius: 8px;
}

.answer h3 {
    color: #66bb6a;
    margin: 0 0 10px;
}

.answer-letter {
    font-size: 28px;
    font-weight: bold;
    color: #66bb6a;
}

.best-move-notation {
    font-size: 18px;
    font-weight: bold;
    color: #66bb6a;
    margin: 10px 0;
}

/* Winning Chances Display */
.winning-chances {
    margin: 20px auto;
    padding: 15px;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 8px;
    text-align: left;
    width: auto;
    display: inline-block;
}

.winning-chances h4 {
    font-size: 18px;
    color: var(--text-fg);
    margin: 0 0 12px 0;
    text-align: center;
}

.chances-grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.chances-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background-color: var(--canvas);
    border: 1px solid var(--border);
    border-radius: 4px;
}

.chances-label {
    font-size: 15px;
    font-weight: 500;
    color: var(--text-fg);
    display: flex;
    align-items: center;
    gap: 6px;
}

.chances-values {
    font-size: 15px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.chances-values strong {
    font-size: 16px;
    color: #4da6ff;
}

.chances-detail {
    font-size: 13px;
    color: #999;
}

/* Analysis Container - for side-by-side layout */
.analysis-container {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    justify-content: center;
    margin: 20px 0;
}

.analysis {
    margin: 20px 0;
    text-align: center;
}

.analysis h4 {
    font-size: 18px;
    color: var(--text-fg);
    margin-bottom: 10px;
    margin-top: 0;
}

/* Side-by-side sections for cube decisions */
.analysis-section,
.chances-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
}

.analysis-section h4,
.chances-section h4 {
    font-size: 18px;
    color: var(--text-fg);
    margin: 0 0 10px 0;
    text-align: center;
}

.click-hint {
    font-size: 12px;
    color: #999;
    font-weight: normal;
    font-style: italic;
}

.moves-table {
    width: auto;
    border-collapse: collapse;
    margin: 10px auto;
    text-align: left;
}

.moves-table th,
.moves-table td {
    padding: 10px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

.moves-table th {
    background-color: var(--canvas-elevated);
    font-weight: bold;
    color: var(--text-fg);
}

.moves-table tr.best-move {
    background-color: rgba(76, 175, 80, 0.15);
    font-weight: bold;
}

.moves-table tr.best-move td {
    color: #66bb6a;
}

.move-row {
    cursor: pointer;
    transition: background-color 0.2s ease;
}

.move-row:hover {
    background-color: rgba(100, 150, 255, 0.1) !important;
}

.move-row.selected {
    background-color: rgba(100, 150, 255, 0.2) !important;
    border-left: 3px solid #4da6ff;
}

.move-row.best-move.selected {
    background-color: rgba(76, 175, 80, 0.25) !important;
    border-left: 3px solid #66bb6a;
}

/* Move W/G/B Side Panel */
.move-wgb-panel {
    position: fixed;
    z-index: 1000;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    min-width: 200px;
    pointer-events: auto;
}

.wgb-panel-content {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.wgb-panel-row {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.wgb-panel-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-fg);
    display: flex;
    align-items: center;
    gap: 4px;
}

.wgb-panel-value {
    font-size: 13px;
    color: var(--text-fg);
    padding-left: 18px;
}

.wgb-panel-value strong {
    font-size: 14px;
    color: #4da6ff;
}

.wgb-highlighted {
    background-color: rgba(100, 150, 255, 0.1) !important;
}

.source-info {
    margin-top: 20px;
    padding: 10px;
    background-color: var(--canvas-elevated);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    color: var(--text-fg);
    text-align: left;
}

.source-info code {
    background-color: var(--canvas-inset);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
    font-size: 11px;
}

/* Position viewer controls */
.position-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 10px 0;
    padding: 8px 12px;
    background-color: var(--canvas-elevated);
    border: 1px solid var(--border);
    border-radius: 4px;
}

#position-status {
    font-size: 14px;
    font-weight: bold;
    color: var(--text-fg);
}

button.toggle-btn,
button.toggle-btn:link,
button.toggle-btn:visited {
    padding: 6px 12px;
    background-color: #4da6ff;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: bold;
    transition: background-color 0.2s ease;
    text-decoration: none;
}

button.toggle-btn:hover {
    background-color: #3d8fcc;
    color: #ffffff;
}

button.toggle-btn:active {
    background-color: #2d7fbc;
    color: #ffffff;
}

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
    padding: 15px 20px;
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
    padding: 15px 20px;
}

.mcq-feedback-incorrect .feedback-icon {
    color: #f44336;
}

.mcq-feedback-incorrect .feedback-text {
    color: #c62828;
}

.feedback-separator {
    margin: 0 12px;
    color: #999;
    font-weight: bold;
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

/* Highlight user's selected move in analysis table */
tr.user-correct {
    background-color: rgba(76, 175, 80, 0.15) !important;
    border-left: 3px solid #4caf50;
}

tr.user-incorrect {
    background-color: rgba(244, 67, 54, 0.15) !important;
    border-left: 3px solid #f44336;
}

.night_mode tr.user-correct {
    background-color: rgba(76, 175, 80, 0.25) !important;
}

.night_mode tr.user-incorrect {
    background-color: rgba(244, 67, 54, 0.25) !important;
}

/* ===================================================================
   ANIMATION STYLES
   =================================================================== */

/* Position viewer animation container */
.position-viewer {
    position: relative;
    overflow: hidden;
}

.position-svg-container {
    transition: opacity 0.3s ease-in-out;
}

/* Smooth fade transitions for position switching */
.position-svg-container.fade-out {
    opacity: 0;
}

.position-svg-container.fade-in {
    opacity: 1;
}

/* Animation controls */
.animation-controls {
    margin: 15px 0;
}

button.animate-btn {
    padding: 8px 16px;
    background-color: #ff9800;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    font-weight: bold;
    transition: background-color 0.2s ease;
    text-decoration: none;
}

button.animate-btn:hover {
    background-color: #f57c00;
    color: #ffffff;
}

button.animate-btn:active {
    background-color: #e65100;
    color: #ffffff;
}

button.animate-btn:disabled {
    background-color: #ccc;
    cursor: not-allowed;
}

/* Checker animation styles */
.checker {
    transition: all 0.3s ease-in-out;
}

/* Support for GSAP animations */
.checker-animated {
    will-change: transform, opacity;
}

/* Animation overlay for temporary animation layer */
#anim-svg-temp {
    pointer-events: none;
    z-index: 100;
}

/* Smooth transitions for SVG visibility */
.position-svg-container[style*="display: none"] {
    display: none !important;
}

.position-svg-container[style*="display: block"] {
    display: block !important;
}
"""
