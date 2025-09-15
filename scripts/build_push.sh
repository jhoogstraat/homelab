#!/bin/bash
docker buildx -f "$1.Dockerfile" --platform=linux/arm64 -t registry.hoogstraat.de/$1:latest --push .