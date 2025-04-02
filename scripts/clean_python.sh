#!/bin/bash
# clean.sh

# Set a very large line length for formatters
LINE_LENGTH=200

# Run formatters with custom line length
isort --line-length $LINE_LENGTH "$@"
black --line-length $LINE_LENGTH "$@"

# For flake8, we need to ignore specific line length errors
flake8 --max-line-length $LINE_LENGTH --ignore=E501 "$@"

