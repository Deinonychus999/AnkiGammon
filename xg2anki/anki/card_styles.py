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
"""
