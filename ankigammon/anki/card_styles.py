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

/* Landscape mode optimizations for mobile devices */
@media screen and (orientation: landscape) and (max-height: 600px) {
    .card {
        padding: 5px 5px;
        max-width: 100%;
    }

    /* Card front - maximize board size */
    .card-front .position-svg svg {
        max-height: 90vh;
        width: auto;
        margin: 2px auto;
        border-width: 1px;
    }

    /* Card back - slightly smaller board to fit analysis */
    .card-back .position-svg svg,
    .card-back .position-svg-container svg,
    .card-back #animated-board svg {
        max-height: 85vh;
        width: auto;
        margin: 2px auto;
        border-width: 1px;
    }

    .metadata {
        margin: 3px 0;
        padding: 5px;
        font-size: 13px;
    }

    .question h3 {
        font-size: 16px;
        margin: 6px 0 5px;
    }

    .mcq-option {
        padding: 8px 12px;
        margin: 4px 0;
        font-size: 14px;
    }

    .mcq-hint {
        margin-top: 6px;
        font-size: 12px;
    }

    .answer {
        margin: 6px 0;
        padding: 8px;
    }

    .answer h3 {
        font-size: 15px;
        margin: 0 0 5px;
    }

    .best-move-notation {
        font-size: 15px;
    }

    .moves-table {
        font-size: 13px;
    }

    .moves-table th,
    .moves-table td {
        padding: 5px 8px;
    }

    .analysis h4 {
        font-size: 15px;
        margin-bottom: 6px;
    }

    .winning-chances {
        padding: 8px;
        margin: 8px auto;
    }

    .winning-chances h4 {
        font-size: 15px;
        margin-bottom: 6px;
    }
}

/* Very small landscape screens (phones in landscape) */
@media screen and (orientation: landscape) and (max-height: 450px) {
    .card {
        padding: 5px 4px;
    }

    /* Card front - maximize board size even on small screens */
    .card-front .position-svg svg {
        max-height: 90vh;
        width: auto;
        margin: 2px auto;
        border-width: 1px;
    }

    /* Card back - balance board with content */
    .card-back .position-svg svg,
    .card-back .position-svg-container svg,
    .card-back #animated-board svg {
        max-height: 80vh;
        width: auto;
        margin: 2px auto;
        border-width: 1px;
    }

    .metadata {
        margin: 2px 0;
        padding: 4px;
        font-size: 12px;
    }

    .question h3 {
        font-size: 14px;
        margin: 4px 0 3px;
    }

    .mcq-option {
        padding: 6px 10px;
        margin: 3px 0;
        font-size: 13px;
    }

    .answer {
        margin: 4px 0;
        padding: 6px;
    }

    .moves-table {
        font-size: 12px;
    }

    .moves-table th,
    .moves-table td {
        padding: 4px 6px;
    }
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

/* Note Section */
.note-section {
    margin: 20px 0;
    padding: 15px;
    background-color: rgba(249, 226, 175, 0.15);
    border: 2px solid #f9e2af;
    border-radius: 8px;
    text-align: left;
}

.note-section h4 {
    color: #c9952a;
    margin: 0 0 10px;
    font-size: 16px;
}

.night_mode .note-section h4 {
    color: #f9e2af;
}

.note-content {
    color: var(--text-fg);
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
}

/* Played Move Indicator */
.played-indicator {
    color: #ff9800;
    font-weight: bold;
    margin-left: 6px;
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
    margin-right: 10px;
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

@media screen and (orientation: landscape) and (max-height: 600px) {

    .note-section {
        margin: 10px 0;
        padding: 8px;
    }

    .note-section h4 {
        font-size: 14px;
        margin-bottom: 6px;
    }

    .note-content {
        font-size: 12px;
    }

    .source-info {
        margin-top: 10px;
        padding: 6px;
        font-size: 11px;
    }

    .mcq-feedback-container {
        margin: 8px 0;
        padding: 8px;
        font-size: 14px;
    }

    .feedback-icon {
        font-size: 28px;
    }
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

/* Move Notation and Inline W/G/B Display */
.move-notation {
    font-weight: bold;
    font-size: 15px;
    margin-bottom: 4px;
}

.move-wgb-inline {
    font-size: 12px;
    line-height: 1.5;
    margin-top: 6px;
}

.wgb-line {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 2px 0;
}

.wgb-line strong {
    color: #4da6ff;
    font-size: 13px;
}

.wgb-detail {
    color: #999;
    font-size: 11px;
    margin-left: 2px;
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

/* XGID copy button */
.xgid-container {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.xgid-text {
    word-break: break-all;
}

.xgid-copy-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
    background-color: var(--canvas-inset);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
    color: var(--text-fg);
    opacity: 0.7;
    transition: opacity 0.2s, background-color 0.2s;
}

.xgid-copy-btn:hover {
    opacity: 1;
    background-color: var(--canvas-elevated);
}

.xgid-copy-btn.copied {
    color: #22c55e;
    opacity: 1;
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

/* Revert to original position icon (at end of row) */
.move-row {
    position: relative;
}

.revert-icon {
    position: absolute;
    right: -36px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    color: #888;
    cursor: pointer;
    border-radius: 4px;
}

.revert-icon:hover {
    color: #4da6ff;
}

.revert-icon svg {
    width: 24px;
    height: 24px;
    fill: currentColor;
}

.revert-icon.showing-original {
    color: #4da6ff;
}

/* ===================================================================
   INTERACTIVE MCQ STYLES
   =================================================================== */

/* MCQ Layout - Default: stacked (options below board) */
.mcq-layout {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
}

.mcq-board-section {
    width: 100%;
}

.mcq-board-section .position-svg {
    display: block;
}

.mcq-board-section .position-svg svg {
    max-width: 100%;
    height: auto;
    margin: 0 auto;
    display: block;
}

.mcq-options-section {
    width: 100%;
    max-width: 500px;
}

/* 2-column grid for options to handle up to 10 choices */
.mcq-options {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
}

.mcq-options-section .metadata {
    margin: 0 0 8px 0;
}

.mcq-options-section .question h3 {
    font-size: 16px;
    margin: 0 0 8px 0;
}

/* Landscape mode: side-by-side layout to maximize limited vertical space */
@media screen and (orientation: landscape) and (max-height: 600px) {
    .interactive-mcq-front {
        display: flex;
        justify-content: center;
    }

    .mcq-layout {
        display: inline-flex;  /* Shrink to fit content */
        flex-direction: row;
        align-items: center;
        gap: 20px;
    }

    .mcq-board-section {
        flex: 0 0 auto;
        width: auto;
    }

    .mcq-board-section .position-svg svg {
        height: 80vh;
        width: auto;
    }

    .mcq-options-section {
        flex: 0 0 auto;
        width: auto;
        min-width: 220px;
        max-width: 320px;
    }

    .mcq-options-section .question h3 {
        font-size: 14px;
        margin: 0 0 6px 0;
    }

    .mcq-options-section .metadata {
        font-size: 12px;
        margin: 0 0 6px 0;
        padding: 6px;
    }

    .mcq-option {
        padding: 6px 8px;
        font-size: 13px;
    }

    .mcq-hint {
        font-size: 11px;
        margin-top: 8px;
    }
}

/* Front Side: Clickable Options */
.mcq-option {
    cursor: pointer;
    padding: 8px 10px;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.15s ease;
    user-select: none;  /* Prevent text selection on click */
    text-align: left;
}

.mcq-option:hover {
    background-color: rgba(100, 150, 255, 0.1);
    border-color: #4da6ff;
}

.mcq-option.selected-flash {
    background-color: rgba(100, 150, 255, 0.3);
    border-color: #4da6ff;
    border-width: 3px;
}

.mcq-option.selected {
    background-color: rgba(100, 150, 255, 0.2);
    border-color: #4da6ff;
    border-width: 3px;
}

/* Hint text below options */
.mcq-hint {
    margin-top: 12px;
    font-size: 12px;
    color: #999;
    font-style: italic;
    text-align: center;
}

/* Submit button for preview mode */
button.mcq-submit-button,
button.mcq-submit-button:link,
button.mcq-submit-button:visited {
    background: #4da6ff;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 12px 24px;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    transition: background-color 0.2s ease;
    text-decoration: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    width: 100%;
    max-width: 300px;
}

button.mcq-submit-button:hover {
    background: #3d8fcc;
    color: #ffffff;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
    transform: translateY(-2px);
}

button.mcq-submit-button:active {
    background: #2d7fbc;
    color: #ffffff;
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

#mcq-submit-container {
    display: flex;
    justify-content: center;
    align-items: center;
}

/* Back Side: Feedback Messages */
.mcq-feedback-container {
    margin: 20px 0;
    padding: 20px;
    border-radius: 8px;
    font-size: 16px;
}

.mcq-feedback-correct,
.mcq-feedback-close,
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

/* Close feedback (orange/yellow - nearly correct) */
.mcq-feedback-close {
    background-color: rgba(255, 152, 0, 0.15);
    border: 2px solid #ff9800;
    padding: 15px 20px;
}

.mcq-feedback-close .feedback-icon {
    color: #ff9800;
}

.mcq-feedback-close .feedback-text {
    color: #ef6c00;
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

.night_mode .mcq-feedback-close {
    background-color: rgba(255, 152, 0, 0.25);
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

tr.user-close {
    background-color: rgba(255, 152, 0, 0.15) !important;
    border-left: 3px solid #ff9800;
}

tr.user-incorrect {
    background-color: rgba(244, 67, 54, 0.15) !important;
    border-left: 3px solid #f44336;
}

.night_mode tr.user-correct {
    background-color: rgba(76, 175, 80, 0.25) !important;
}

.night_mode tr.user-close {
    background-color: rgba(255, 152, 0, 0.25) !important;
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

/* ===================================================================
   SCORE MATRIX STYLES
   =================================================================== */

.score-matrix {
    margin: 30px auto 20px;
    text-align: center;
}

.score-matrix h3 {
    font-size: 18px;
    color: var(--text-fg);
    margin-bottom: 15px;
}

.score-matrix h3 .ply-indicator {
    font-size: 14px;
    opacity: 0.6;
    font-weight: normal;
}

.score-matrix-table {
    border-collapse: collapse;
    margin: 0 auto;
    font-size: 13px;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
}

.score-matrix-table th {
    background-color: var(--canvas-elevated);
    color: var(--text-fg);
    font-weight: bold;
    padding: 8px 12px;
    border: 1px solid var(--border);
}

.score-matrix-table td {
    padding: 8px 12px;
    border: 1px solid var(--border);
    text-align: center;
    min-width: 70px;
}

/* Cube action color coding */
.score-matrix-table .action-double-take {
    background-color: rgba(76, 175, 80, 0.3);
}

.score-matrix-table .action-double-pass {
    background-color: rgba(255, 152, 0, 0.3);
}

.score-matrix-table .action-no-double {
    background-color: rgba(33, 150, 243, 0.3);
}

.score-matrix-table .action-too-good {
    background-color: rgba(156, 39, 176, 0.3);
}

.score-matrix-table .action-no-alternatives {
    background-color: rgba(158, 158, 158, 0.15);
    color: #999;
}

/* Low error cells - more transparent to show it's a close decision */
.score-matrix-table .action-double-take.low-error {
    background-color: rgba(76, 175, 80, 0.12);
}

.score-matrix-table .action-double-pass.low-error {
    background-color: rgba(255, 152, 0, 0.12);
}

.score-matrix-table .action-no-double.low-error {
    background-color: rgba(33, 150, 243, 0.12);
}

.score-matrix-table .action-too-good.low-error {
    background-color: rgba(156, 39, 176, 0.12);
}

/* Current score cell highlight */
.score-matrix-table .current-score {
    border: 3px solid #FFD700;
    box-shadow: 0 0 8px rgba(255, 215, 0, 0.6);
}

/* Matrix cell content */
.score-matrix-table .action {
    font-weight: bold;
    font-size: 14px;
    margin-bottom: 4px;
}

.score-matrix-table .errors {
    font-size: 11px;
    color: #666;
}

.night_mode .score-matrix-table .errors {
    color: #aaa;
}

/* Dark mode adjustments */
.night_mode .score-matrix-table .action-double-take {
    background-color: rgba(76, 175, 80, 0.4);
}

.night_mode .score-matrix-table .action-double-pass {
    background-color: rgba(255, 152, 0, 0.4);
}

.night_mode .score-matrix-table .action-no-double {
    background-color: rgba(33, 150, 243, 0.4);
}

.night_mode .score-matrix-table .action-too-good {
    background-color: rgba(156, 39, 176, 0.4);
}

.night_mode .score-matrix-table .action-no-alternatives {
    background-color: rgba(158, 158, 158, 0.25);
    color: #bbb;
}

/* Dark mode low error cells */
.night_mode .score-matrix-table .action-double-take.low-error {
    background-color: rgba(76, 175, 80, 0.15);
}

.night_mode .score-matrix-table .action-double-pass.low-error {
    background-color: rgba(255, 152, 0, 0.15);
}

.night_mode .score-matrix-table .action-no-double.low-error {
    background-color: rgba(33, 150, 243, 0.15);
}

.night_mode .score-matrix-table .action-too-good.low-error {
    background-color: rgba(156, 39, 176, 0.15);
}

/* Score matrix optimizations for landscape mode */
@media screen and (orientation: landscape) and (max-height: 600px) {
    .score-matrix {
        margin: 15px auto 10px;
    }

    .score-matrix h3 {
        font-size: 14px;
        margin-bottom: 8px;
    }

    .score-matrix h3 .ply-indicator {
        font-size: 11px;
    }

    .score-matrix-table {
        font-size: 11px;
    }

    .score-matrix-table th,
    .score-matrix-table td {
        padding: 4px 6px;
        min-width: 50px;
    }

    .score-matrix-table .action {
        font-size: 12px;
        margin-bottom: 2px;
    }

    .score-matrix-table .errors {
        font-size: 10px;
    }
}

/* Hide score matrix on very small landscape screens to prevent scrolling */
@media screen and (orientation: landscape) and (max-height: 450px) {
    .score-matrix {
        display: none;
    }
}

/* ===================================================================
   MOVE SCORE MATRIX STYLES
   Shows top moves at different score contexts (Neutral, DMP, G-Save, G-Go)
   =================================================================== */

.move-score-matrix {
    margin: 30px auto 20px;
    text-align: center;
}

.move-score-matrix h3 {
    font-size: 18px;
    color: var(--text-fg);
    margin-bottom: 15px;
}

.move-score-matrix h3 .ply-indicator {
    font-size: 14px;
    opacity: 0.6;
    font-weight: normal;
}

.move-score-matrix-table {
    border-collapse: collapse;
    margin: 0 auto;
    font-size: 14px;
    background-color: var(--canvas-elevated);
    border: 2px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    table-layout: fixed;
    width: auto;
}

.move-score-matrix-table thead th {
    background-color: var(--canvas-elevated);
    color: var(--text-fg);
    font-weight: bold;
    padding: 10px 14px;
    border: 1px solid var(--border);
    min-width: 110px;
    max-width: 150px;
    font-size: 14px;
}

.move-score-matrix-table td {
    padding: 8px 12px;
    border: 1px solid var(--border);
    text-align: center;
    vertical-align: top;
    font-size: 13px;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

/* Move notation styling */
.move-score-matrix-table .move-notation {
    font-weight: 500;
    margin-bottom: 3px;
    font-size: 13px;
    white-space: nowrap;
}

/* Equity and error display */
.move-score-matrix-table .equity-error {
    font-size: 12px;
}

.move-score-matrix-table .equity {
    color: #4caf50;
}

.move-score-matrix-table .error {
    color: #888;
}

.move-score-matrix-table .no-move {
    color: #666;
}

/* Best move (rank 1) row styling */
.move-score-matrix-table tr.rank-1 td {
    background-color: rgba(76, 175, 80, 0.15);
}

.move-score-matrix-table tr.rank-1 .move-notation {
    font-weight: bold;
}

/* Highlight columns where best move differs from Neutral */
.move-score-matrix-table td.different-best {
    background-color: rgba(255, 193, 7, 0.2) !important;
    border: 2px solid #FFC107 !important;
}

/* Dark mode adjustments */
.night_mode .move-score-matrix-table {
    background-color: var(--canvas-elevated);
    border-color: var(--border);
}

.night_mode .move-score-matrix-table thead th {
    background-color: var(--canvas-elevated);
    border-color: var(--border);
}

.night_mode .move-score-matrix-table td {
    border-color: var(--border);
}

.night_mode .move-score-matrix-table tr.rank-1 td {
    background-color: rgba(76, 175, 80, 0.25);
}

.night_mode .move-score-matrix-table td.different-best {
    background-color: rgba(255, 193, 7, 0.3) !important;
}

.night_mode .move-score-matrix-table .error {
    color: #aaa;
}

.night_mode .move-score-matrix-table .no-move {
    color: #888;
}

/* Move score matrix optimizations for landscape mode */
@media screen and (orientation: landscape) and (max-height: 600px) {
    .move-score-matrix {
        margin: 15px auto 10px;
    }

    .move-score-matrix h3 {
        font-size: 14px;
        margin-bottom: 8px;
    }

    .move-score-matrix h3 .ply-indicator {
        font-size: 11px;
    }

    .move-score-matrix-table {
        font-size: 10px;
    }

    .move-score-matrix-table thead th {
        padding: 6px 8px;
        min-width: 80px;
    }

    .move-score-matrix-table td {
        padding: 4px 6px;
    }

    .move-score-matrix-table .move-notation {
        font-size: 10px;
    }

    .move-score-matrix-table .equity-error {
        font-size: 9px;
    }
}

/* Hide move score matrix on very small landscape screens */
@media screen and (orientation: landscape) and (max-height: 450px) {
    .move-score-matrix {
        display: none;
    }
}

/* Mobile responsive - compact move score matrix */
@media screen and (max-width: 500px) {
    .move-score-matrix-table thead th {
        padding: 6px 6px;
        min-width: 70px;
        font-size: 11px;
    }

    .move-score-matrix-table th .score-desc {
        font-size: 9px;
    }

    .move-score-matrix-table td {
        padding: 4px 4px;
    }

    .move-score-matrix-table .move-notation {
        font-size: 10px;
    }

    .move-score-matrix-table .equity-error {
        font-size: 9px;
    }
}

/* ===================================================================
   MOBILE PORTRAIT RESPONSIVE STYLES
   =================================================================== */

/* Mobile screens */
@media screen and (max-width: 615px) {
    .card {
        padding: 10px;
        max-width: 100%;
    }

    /* Stack analysis and winning chances vertically */
    .analysis-container {
        flex-direction: column;
        gap: 15px;
        align-items: center;
    }

    /* Make tables responsive with horizontal scroll */
    .analysis,
    .analysis-section {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    .moves-table {
        min-width: 280px;
        font-size: 14px;
    }

    .moves-table th,
    .moves-table td {
        padding: 8px 6px;
    }

    .move-notation {
        font-size: 14px;
    }

    .move-wgb-inline {
        font-size: 11px;
    }

    .wgb-detail {
        font-size: 10px;
    }

    /* Winning chances responsive */
    .winning-chances {
        padding: 12px;
        margin: 10px 0;
    }

    .chances-detail {
        font-size: 11px;
    }

    /* Answer section */
    .answer {
        padding: 12px;
        margin: 15px 0;
    }

    .answer h3 {
        font-size: 16px;
    }

    .best-move-notation {
        font-size: 16px;
    }

    /* Metadata */
    .metadata {
        font-size: 13px;
        padding: 8px;
    }

    /* Analysis title */
    .analysis h4,
    .analysis-section h4,
    .chances-section h4 {
        font-size: 16px;
    }

    /* Score matrix */
    .score-matrix {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    .score-matrix-table {
        font-size: 11px;
    }

    .score-matrix-table th,
    .score-matrix-table td {
        padding: 5px 4px;
        min-width: 55px;
    }

    /* Source info */
    .source-info {
        font-size: 11px;
        padding: 8px;
    }

    .source-info code {
        font-size: 10px;
        word-break: break-all;
    }

    /* MCQ feedback */
    .mcq-feedback-container {
        padding: 12px;
    }

    .feedback-icon {
        font-size: 32px;
    }

    .feedback-text {
        font-size: 14px;
    }

    .feedback-separator {
        display: block;
        margin: 4px 0;
    }

    /* Note section */
    .note-section {
        padding: 10px;
    }

    .note-section h4 {
        font-size: 14px;
    }

    .note-content {
        font-size: 13px;
    }
}

/* Small mobile screens (portrait) */
@media screen and (max-width: 380px) {
    .card {
        padding: 8px;
    }

    .moves-table {
        font-size: 12px;
    }

    .moves-table th,
    .moves-table td {
        padding: 6px 4px;
    }

    .move-notation {
        font-size: 13px;
    }

    .winning-chances {
        padding: 10px;
    }

    .chances-values strong {
        font-size: 14px;
    }

    .chances-detail {
        font-size: 10px;
    }

    .answer h3 {
        font-size: 15px;
    }

    .best-move-notation {
        font-size: 15px;
    }

    .score-matrix-table th,
    .score-matrix-table td {
        padding: 4px 3px;
        min-width: 45px;
    }

    .score-matrix-table .action {
        font-size: 11px;
    }

    .score-matrix-table .errors {
        font-size: 9px;
    }
}
"""
