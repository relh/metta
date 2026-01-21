#!/bin/bash
# Runs on HOST before container creation to ensure mount directories exist

mkdir -p ~/.claude
mkdir -p ~/.codex
mkdir -p ~/.config/gh
mkdir -p ~/.config/gcloud
mkdir -p ~/.config/wandb
mkdir -p ~/.config/graphite
mkdir -p ~/.config/devdotfiles
mkdir -p ~/.sky
touch ~/.netrc
