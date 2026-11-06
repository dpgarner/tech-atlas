"""Entity resolution: fold raw 'brand' strings into canonical technology keys.

The hard part of a bookmark corpus is that the *same* technology shows up as
many brands: react.dev, reactjs.org, github.com/facebook/react, a folder named
"React". This module maps every observed brand to one canonical key so counts
and relations aggregate instead of fragmenting.
"""
from __future__ import annotations

import json
import os
import re


SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")

DEFAULT_ALIASES = {
    "react": "react", "reactjs": "react", "react-native": "react",
    "node": "node", "nodejs": "node", "npm": "node",
    "next": "nextjs", "nextjs": "nextjs",
    "vue": "vue", "vuejs": "vue",
    "angular": "angular", "angularjs": "angular",
    "svelte": "svelte", "sveltejs": "svelte",
    "tailwind": "tailwind", "tailwindcss": "tailwind",
    "js": "javascript", "javascript": "javascript", "ecmascript": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "python": "python", "python3": "python",
    "go": "go", "golang": "go",
    "rust": "rust", "rust-lang": "rust",
    "java": "java", "kotlin": "kotlin", "swift": "swift",
    "dotnet": "dotnet", "csharp": "dotnet",
    "cpp": "cpp", "cplusplus": "cpp",
    "docker": "docker", "dockerhub": "docker",
    "kubernetes": "kubernetes", "k8s": "kubernetes",
    "postgres": "postgres", "postgresql": "postgres", "psql": "postgres",
    "mysql": "mysql", "mariadb": "mysql",
    "mongo": "mongodb", "mongodb": "mongodb",
    "redis": "redis", "sqlite": "sqlite", "elasticsearch": "elasticsearch",
    "kafka": "kafka", "rabbitmq": "rabbitmq", "clickhouse": "clickhouse", "duckdb": "duckdb",
    "nginx": "nginx", "apache": "apache", "caddy": "caddy",
    "aws": "aws", "amazon": "aws", "azure": "azure", "microsoft": "microsoft",
    "google": "google", "gcp": "gcp", "cloudflare": "cloudflare", "vercel": "vercel",
    "netlify": "netlify", "github": "github", "gitlab": "gitlab",
    "openai": "openai", "anthropic": "anthropic", "claude": "anthropic",
    "deepseek": "deepseek", "qwen": "qwen", "llama": "llama", "meta": "meta",
    "mistral": "mistral", "mistralai": "mistral", "gemini": "gemini",
    "ollama": "ollama", "huggingface": "huggingface", "pytorch": "pytorch",
    "tensorflow": "tensorflow", "langchain": "langchain", "llamaindex": "llamaindex",
    "chroma": "chroma", "pinecone": "pinecone", "weaviate": "weaviate", "qdrant": "qdrant",
    "vscode": "vscode", "vim": "vim", "neovim": "neovim", "jetbrains": "jetbrains",
    "graphql": "graphql", "grpc": "grpc", "rest": "rest", "protobuf": "protobuf",
    "linux": "linux", "ubuntu": "ubuntu", "debian": "debian", "windows": "windows",
    "terraform": "terraform", "ansible": "ansible", "pulumi": "pulumi",
    "vite": "vite", "webpack": "webpack", "rollup": "rollup", "esbuild": "esbuild",
    "astro": "astro", "remix": "remix", "nuxt": "nuxt", "django": "django",
    "flask": "flask", "fastapi": "fastapi", "rails": "rails", "laravel": "laravel",
    "spring": "spring", "quarkus": "quarkus", "deno": "deno", "bun": "bun",
}

DISPLAY = {
    "react": "React", "node": "Node.js", "nextjs": "Next.js", "vue": "Vue",
    "angular": "Angular", "svelte": "Svelte", "tailwind": "Tailwind CSS",
    "javascript": "JavaScript", "typescript": "TypeScript", "python": "Python",
    "go": "Go", "rust": "Rust", "cpp": "C++", "dotnet": ".NET", "csharp": "C#",
    "postgres": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes", "aws": "AWS", "gcp": "Google Cloud",
    "vscode": "VS Code", "openai": "OpenAI", "anthropic": "Anthropic",
    "huggingface": "Hugging Face", "pytorch": "PyTorch", "tensorflow": "TensorFlow",
    "graphql": "GraphQL", "grpc": "gRPC", "nocodb": "NocoDB", "llamaindex": "LlamaIndex",
}

# Seed category taxonomy: tech key -> high-level bucket ("how it relates").
DEFAULT_CATEGORIES = {
    "react": "frontend", "vue": "frontend", "svelte": "frontend", "angular": "frontend",
    "nextjs": "frontend", "astro": "frontend", "remix": "frontend", "nuxt": "frontend",
    "tailwind": "frontend", "vite": "frontend", "webpack": "frontend", "esbuild": "frontend",
    "node": "runtime", "deno": "runtime", "bun": "runtime",
    "javascript": "language", "typescript": "language", "python": "language",
    "go": "language", "rust": "language", "java": "language", "kotlin": "language",
    "swift": "language", "cpp": "language", "dotnet": "language",
    "docker": "infra", "kubernetes": "infra", "nginx": "infra", "caddy": "infra",
    "terraform": "infra", "ansible": "infra", "pulumi": "infra", "cloudflare": "infra",
    "postgres": "database", "mysql": "database", "mongodb": "database",
    "redis": "database", "sqlite": "database", "elasticsearch": "database",
    "clickhouse": "database", "duckdb": "database", "kafka": "database", "rabbitmq": "database",
    "aws": "cloud", "azure": "cloud", "gcp": "cloud", "vercel": "cloud", "netlify": "cloud",
    "openai": "ai", "anthropic": "ai", "deepseek": "ai", "qwen": "ai", "llama": "ai",
    "mistral": "ai", "gemini": "ai", "ollama": "ai", "huggingface": "ai",
    "pytorch": "ai", "tensorflow": "ai", "langchain": "ai", "llamaindex": "ai",
    "chroma": "ai", "pinecone": "ai", "weaviate": "ai", "qdrant": "ai",
    "github": "platform", "gitlab": "platform", "microsoft": "platform", "google": "platform",
    "vscode": "tooling", "vim": "tooling", "neovim": "tooling", "jetbrains": "tooling",
    "django": "backend", "flask": "backend", "fastapi": "backend", "rails": "backend",
    "laravel": "backend", "spring": "backend", "quarkus": "backend",
    "graphql": "protocol", "grpc": "protocol", "rest": "protocol", "protobuf": "protocol",
    "linux": "os", "ubuntu": "os", "debian": "os", "windows": "os",
}


def _load_seed(name: str, default: dict) -> dict:
    path = os.path.join(SEED_DIR, name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            merged = dict(default)
            merged.update({str(k).lower(): str(v).lower() for k, v in data.items()})
            return merged
        except (ValueError, OSError):
            pass
    return dict(default)


class Resolver:
    def __init__(self, aliases=None, categories=None):
        self.aliases = _load_seed("aliases.json", DEFAULT_ALIASES) if aliases is None else dict(aliases)
        self.categories = _load_seed("categories.json", DEFAULT_CATEGORIES) if categories is None else dict(categories)

    def key(self, brand: str) -> str:
        b = (brand or "").strip().lower()
        if not b:
            return "unknown"
        if b in self.aliases:
            return self.aliases[b]
        # Try trimmed variants: 'reactjs-org' -> 'reactjs'
        for sep in ("-", "_", "."):
            if sep in b:
                head = b.split(sep)[0]
                if head in self.aliases:
                    return self.aliases[head]
        return b

    def name(self, key: str) -> str:
        if key in DISPLAY:
            return DISPLAY[key]
        parts = re.split(r"[-_.]", key)
        return " ".join(p[:1].upper() + p[1:] for p in parts if p)

    def kind(self, key: str) -> str:
        return self.categories.get(key, "site")
