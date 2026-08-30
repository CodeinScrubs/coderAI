import pytest
from syntax_chunker import SyntaxChunker


def test_python_chunking():
    code = """
import os

def calculate_sum(a: int, b: int) -> int:
    \"\"\"Calculates sum of two integers.\"\"\"
    return a + b

class DatabaseClient:
    def __init__(self, host: str):
        self.host = host

    async def connect(self):
        pass
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("app/main.py", code, 1000.0)
    assert len(chunks) >= 2
    names = {c.symbol_name for c in chunks if c.symbol_name}
    assert "calculate_sum" in names
    assert "DatabaseClient" in names
    sum_chunk = next(c for c in chunks if c.symbol_name == "calculate_sum")
    assert sum_chunk.symbol_type == "function"
    assert sum_chunk.docstring == "Calculates sum of two integers."


def test_javascript_typescript_chunking():
    ts_code = """
import { useState } from 'react';

/**
 * User profile interface
 */
export interface UserProfile {
    id: string;
    username: string;
    email: string;
}

export class UserService {
    private apiUrl: string;

    constructor(apiUrl: string) {
        this.apiUrl = apiUrl;
    }

    async fetchUser(id: string): Promise<UserProfile> {
        const res = await fetch(`${this.apiUrl}/users/${id}`);
        return res.json();
    }
}

export const formatUserName = (user: UserProfile) => {
    return `${user.username} (${user.id})`;
};
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("src/services/userService.ts", ts_code, 1000.0)
    assert len(chunks) >= 3
    names = {c.symbol_name for c in chunks if c.symbol_name}
    assert "UserProfile" in names
    assert "UserService" in names
    assert "formatUserName" in names
    
    interface_chunk = next(c for c in chunks if c.symbol_name == "UserProfile")
    assert interface_chunk.symbol_type == "interface"


def test_go_chunking():
    go_code = """
package main

import "fmt"

type ServerConfig struct {
    Port int
    Host string
}

func NewServer(port int) *ServerConfig {
    return &ServerConfig{Port: port, Host: "127.0.0.1"}
}

func (s *ServerConfig) Start() error {
    fmt.Printf("Starting on %s:%d\\n", s.Host, s.Port)
    return nil
}
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("cmd/server.go", go_code, 1000.0)
    names = {c.symbol_name for c in chunks if c.symbol_name}
    assert "ServerConfig" in names
    assert "NewServer" in names
    assert "Start" in names


def test_rust_chunking():
    rust_code = """
pub struct Point {
    pub x: f64,
    pub y: f64,
}

pub enum Direction {
    North,
    South,
    East,
    West,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }
}

pub async fn compute_distance(p1: &Point, p2: &Point) -> f64 {
    ((p1.x - p2.x).powi(2) + (p1.y - p2.y).powi(2)).sqrt()
}
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("src/geometry.rs", rust_code, 1000.0)
    names = {c.symbol_name for c in chunks if c.symbol_name}
    assert "Point" in names
    assert "Direction" in names
    assert "compute_distance" in names


def test_java_chunking():
    java_code = """
package com.example.app;

public class OrderProcessor {
    private String orderId;

    public OrderProcessor(String orderId) {
        this.orderId = orderId;
    }

    public boolean processPayment(double amount) {
        if (amount <= 0) {
            return false;
        }
        return true;
    }
}
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("OrderProcessor.java", java_code, 1000.0)
    names = {c.symbol_name for c in chunks if c.symbol_name}
    assert "OrderProcessor" in names


def test_markdown_chunking():
    md = """
# Getting Started
This is the intro.

## Installation
Run npm install.

## Configuration
Configure environment variables.
"""
    chunker = SyntaxChunker()
    chunks = chunker.chunk("docs/README.md", md, 1000.0)
    assert len(chunks) >= 3
    names = [c.symbol_name for c in chunks]
    assert "Getting Started" in names
    assert "Installation" in names
    assert "Configuration" in names
