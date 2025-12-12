#!/bin/bash
# Run tests with proper Python path

# Set PYTHONPATH to project root
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Run tests
if [ $# -eq 0 ]; then
    # No arguments - run all tests
    python -m pytest tests/ -v
else
    # Run specific test file
    python -m pytest "$@" -v
fi