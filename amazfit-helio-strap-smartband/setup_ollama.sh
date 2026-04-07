#!/bin/bash
# Setup Ollama with medical AI models for health data analysis
# Usage: ./setup_ollama.sh

set -e

echo "=== Ollama Medical Model Setup ==="
echo ""

# Check if ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Installing..."
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install ollama
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
fi

echo "Ollama version: $(ollama --version 2>/dev/null || echo 'unknown')"
echo ""

# Start ollama serve if not running
if ! curl -s http://localhost:11434/api/version &>/dev/null; then
    echo "Starting Ollama server..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 3
    if ! curl -s http://localhost:11434/api/version &>/dev/null; then
        echo "ERROR: Failed to start Ollama server"
        exit 1
    fi
    echo "Ollama server started (PID $OLLAMA_PID)"
else
    echo "Ollama server already running"
fi
echo ""

# Available medical models
echo "Available medical models:"
echo "  1) MedAIBase/medgemma1.5:4b (~3 GB)  - Recommended medical Gemma 1.5"
echo "  2) medllama2               (~4 GB)  - Llama 2 fine-tuned on MedQA"
echo "  3) Both"
echo ""

read -p "Select model(s) to install [1]: " CHOICE
CHOICE=${CHOICE:-1}

case $CHOICE in
    1)
        MODELS="MedAIBase/medgemma1.5:4b"
        ;;
    2)
        MODELS="medllama2"
        ;;
    3)
        MODELS="MedAIBase/medgemma1.5:4b medllama2"
        ;;
    *)
        echo "Invalid choice, defaulting to MedAIBase/medgemma1.5:4b"
        MODELS="MedAIBase/medgemma1.5:4b"
        ;;
esac

echo ""
for MODEL in $MODELS; do
    echo "Pulling $MODEL..."
    ollama pull "$MODEL"
    echo "$MODEL installed successfully"
    echo ""
done

# Verify
echo "=== Installed Models ==="
ollama list
echo ""

# Quick test
FIRST_MODEL=$(echo $MODELS | awk '{print $1}')
echo "=== Quick Test: $FIRST_MODEL ==="
echo "Sending test prompt..."
RESPONSE=$(curl -s http://localhost:11434/api/chat \
    -d "{\"model\": \"$FIRST_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"In one sentence, what is a normal resting heart rate?\"}], \"stream\": false}" \
    2>/dev/null)

if echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['message']['content'])" 2>/dev/null; then
    echo ""
    echo "Model is working!"
else
    echo "WARNING: Model test failed. It may still be loading."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "NOTE: MedPaLM is NOT available on Ollama (it's a closed Google Cloud model)."
echo "medgemma and medllama2 are the best open-source medical models available."
echo ""
echo "To use in the app:"
echo "  1. Keep 'ollama serve' running"
echo "  2. Open the dashboard and use the 'AI Health Analysis' panel"
echo "  3. The default model is 'medgemma' — change it in the panel if needed"
echo ""
echo "DISCLAIMER: AI analysis is for informational purposes only."
echo "Always consult a healthcare professional for medical advice."
