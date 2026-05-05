#!/bin/bash

# Fix Go environment (Homebrew vs /usr/local/go conflict)
export GOROOT=/opt/homebrew/Cellar/go/1.26.2/libexec
export PATH="$GOROOT/bin:$PATH"

# Create tmp directory if it doesn't exist
mkdir -p tmp

# Run Air for live reloading
air

