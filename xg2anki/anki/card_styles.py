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

.position-image img {
    max-width: 100%;
    height: auto;
    border: 2px solid var(--border);
    border-radius: 8px;
    margin: 10px 0;
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

.analysis {
    margin: 20px 0;
    text-align: center;
}

.analysis h4 {
    font-size: 18px;
    color: var(--text-fg);
    margin-bottom: 10px;
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
.position-viewer {
    position: relative;
}

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
"""
