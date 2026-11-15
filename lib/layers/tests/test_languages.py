"""One small project per language that is read from its text.

Each has a layer `core` and a layer `adapters` that may use core. Core uses
adapters, which must be reported; adapters use core, which must not; and core
touches something a pure layer may not, or a package it forbids.

Run with: PYTHONPATH=. python -m unittest discover -s tests
"""

import json
import textwrap
import unittest

from test_layers import call, found, run, tree

from layers import cli
from layers.generic import Syntax, blank
from layers.languages import LANGUAGES


def rules(core: str, adapters: str, *, pure: bool = True, forbid: tuple[str, ...] = ()) -> str:
    listed = ", ".join(f'"{entry}"' for entry in forbid)
    return textwrap.dedent(
        f"""
        [[layer]]
        name = "core"
        paths = [{core}]
        pure = {"true" if pure else "false"}
        forbid_external = [{listed}]

        [[layer]]
        name = "adapters"
        paths = [{adapters}]
        may_use = ["core"]
        """
    )


def layer(source: str, target: str) -> tuple[str, str, str]:
    return ("layer", source, target)


def purity(source: str, what: str) -> tuple[str, str, str]:
    return ("purity", source, what)


def external(source: str, what: str) -> tuple[str, str, str]:
    return ("external", source, what)


# name -> (files, what must be reported)
CASES: dict[str, tuple[dict[str, str], set[tuple[str, str, str]]]] = {
    "go": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "go.mod": "module example.com/shop\n\ngo 1.22\n",
            "core/price.go": """
                package core

                import (
                    "os"
                    "strings"

                    // "example.com/shop/ignored"
                    store "example.com/shop/adapters"
                )

                func Total() int { store.Save(); return len(os.Args) + len(strings.TrimSpace("import \\"net\\"")) }
            """,
            "adapters/store.go": """
                package adapters

                import "example.com/shop/core"

                func Save() { _ = core.Total }
            """,
        },
        {layer("core/price.go", "adapters/store.go"), purity("core/price.go", "os")},
    ),
    "java": (
        {
            "architecture.toml": rules('"src/main/java/shop/core/**"', '"src/main/java/shop/adapters/**"'),
            "src/main/java/shop/core/Price.java": """
                package shop.core;

                import shop.adapters.Store;
                import java.io.File;
                import java.util.List;

                /* import shop.adapters.Nothing; */
                public class Price { long now() { return System.currentTimeMillis(); } }
            """,
            "src/main/java/shop/adapters/Store.java": """
                package shop.adapters;

                import static shop.core.Price.now;

                public class Store { }
            """,
        },
        {
            layer("src/main/java/shop/core/Price.java", "src/main/java/shop/adapters/Store.java"),
            purity("src/main/java/shop/core/Price.java", "java.io"),
            purity("src/main/java/shop/core/Price.java", "clock"),
        },
    ),
    "kotlin": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "src/shop/core/Price.kt": """
                package shop.core

                import shop.adapters.Store
                import kotlin.io.path.Path

                fun total() { println("x") }
            """,
            "src/shop/adapters/Store.kt": """
                package shop.adapters

                import shop.core.*

                class Store
            """,
        },
        {
            layer("src/shop/core/Price.kt", "src/shop/adapters/Store.kt"),
            purity("src/shop/core/Price.kt", "kotlin.io"),
            purity("src/shop/core/Price.kt", "console"),
        },
    ),
    "groovy": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "src/shop/core/Price.groovy": """
                package shop.core

                import shop.adapters.Store
                import groovy.sql.Sql

                class Price { }
            """,
            "src/shop/adapters/Store.groovy": """
                package shop.adapters

                import shop.core.Price

                class Store { }
            """,
        },
        {layer("src/shop/core/Price.groovy", "src/shop/adapters/Store.groovy"), purity("src/shop/core/Price.groovy", "groovy.sql")},
    ),
    "scala": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "src/shop/core/Price.scala": """
                package shop
                package core

                import shop.adapters.{Store, Other => Renamed}
                import scala.io.Source

                object Price
            """,
            "src/shop/adapters/Store.scala": """
                package shop.adapters

                import shop.core._

                class Store
            """,
        },
        {layer("src/shop/core/Price.scala", "src/shop/adapters/Store.scala"), purity("src/shop/core/Price.scala", "scala.io")},
    ),
    "csharp": (
        {
            "architecture.toml": rules('"Core/**"', '"Adapters/**"'),
            "Core/Price.cs": """
                using System;
                using System.IO;
                using Shop.Adapters;

                namespace Shop.Core;

                public class Price { public DateTime At() { using var x = new MemoryStream(); return DateTime.UtcNow; } }
            """,
            "Adapters/Store.cs": """
                namespace Shop.Adapters
                {
                    using Shop.Core;

                    public class Store { }
                }
            """,
        },
        {layer("Core/Price.cs", "Adapters/Store.cs"), purity("Core/Price.cs", "System.IO"), purity("Core/Price.cs", "clock")},
    ),
    "fsharp": (
        {
            "architecture.toml": rules('"Core/**"', '"Adapters/**"'),
            "Core/Price.fs": """
                module Shop.Core.Price

                open Shop.Adapters

                let total = 1
                let show () = printfn "x"
            """,
            "Adapters/Store.fs": """
                namespace Shop.Adapters

                open Shop.Core

                module Store =
                    let save () = Shop.Core.Price.total
            """,
        },
        {layer("Core/Price.fs", "Adapters/Store.fs"), purity("Core/Price.fs", "console")},
    ),
    "swift": (
        {
            "architecture.toml": rules('"Sources/Core/**"', '"Sources/Adapters/**"'),
            "Sources/Core/Price.swift": """
                import Foundation
                @testable import Adapters

                func total() { print("x") }
            """,
            "Sources/Adapters/Store.swift": """
                import Core
                import Network
            """,
        },
        {layer("Sources/Core/Price.swift", "Sources/Adapters/Store.swift"), purity("Sources/Core/Price.swift", "console")},
    ),
    "dart": (
        {
            "architecture.toml": rules('"lib/core/**"', '"lib/adapters/**"'),
            "pubspec.yaml": "name: shop\n",
            "lib/core/price.dart": """
                import 'package:shop/adapters/store.dart';
                import 'dart:io';
                import 'dart:math';
                import 'package:collection/collection.dart';
            """,
            "lib/adapters/store.dart": """
                import '../core/price.dart';
            """,
        },
        {layer("lib/core/price.dart", "lib/adapters/store.dart"), purity("lib/core/price.dart", "dart:io")},
    ),
    "php": (
        {
            "architecture.toml": rules('"src/Core/**"', '"src/Adapters/**"'),
            "src/Core/Price.php": """
                <?php
                namespace Shop\\Core;

                use Shop\\Adapters\\Store;
                use GuzzleHttp\\Client;

                class Price { function now() { return time(); } }
            """,
            "src/Adapters/Store.php": """
                <?php
                namespace Shop\\Adapters;

                require_once __DIR__ . '/../Core/Price.php';

                class Store { function price() { return new \\Shop\\Core\\Price(); } }
            """,
        },
        {
            layer("src/Core/Price.php", "src/Adapters/Store.php"),
            purity("src/Core/Price.php", "GuzzleHttp"),
            purity("src/Core/Price.php", "clock"),
        },
    ),
    "ruby": (
        {
            "architecture.toml": rules('"lib/shop/core/**"', '"lib/shop/adapters/**"'),
            "lib/shop/core/price.rb": """
                require_relative "../adapters/store"
                require "net/http"

                module Shop
                  module Core
                    class Price
                      def now = Time.now
                    end
                  end
                end
            """,
            "lib/shop/core/tax.rb": """
                # A constant alone names the file, the way Zeitwerk loads it.
                module Shop
                  module Core
                    class Tax
                      def store = Shop::Adapters::Store.new
                    end
                  end
                end
            """,
            "lib/shop/adapters/store.rb": """
                require "shop/core/price"

                module Shop
                  module Adapters
                    class Store
                      def price = Shop::Core::Price.new
                    end
                  end
                end
            """,
        },
        {
            layer("lib/shop/core/price.rb", "lib/shop/adapters/store.rb"),
            layer("lib/shop/core/tax.rb", "lib/shop/adapters/store.rb"),
            purity("lib/shop/core/price.rb", "net/http"),
            purity("lib/shop/core/price.rb", "clock"),
        },
    ),
    "elixir": (
        {
            "architecture.toml": rules('"lib/shop/core/**"', '"lib/shop/adapters/**"'),
            "lib/shop/core/price.ex": '''
                defmodule Shop.Core.Price do
                  @moduledoc """
                  Not a use: alias Shop.Adapters.Ghost
                  """
                  alias Shop.Adapters.Store

                  def total, do: Store.save(File.read!("x"))
                  def seed, do: :rand.uniform()
                end
            ''',
            "lib/shop/adapters/store.ex": """
                defmodule Shop.Adapters.Store do
                  def save(_), do: Shop.Core.Price.total()
                end
            """,
        },
        {
            layer("lib/shop/core/price.ex", "lib/shop/adapters/store.ex"),
            purity("lib/shop/core/price.ex", "File"),
            purity("lib/shop/core/price.ex", ":rand"),
        },
    ),
    "erlang": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.erl": """
                -module(price).
                -export([total/0]).
                %% store_ghost:save() is only a comment.
                total() -> store:save(file:read_file("x")).
            """,
            "src/adapters/store.erl": """
                -module(store).
                -export([save/1]).
                save(_) -> price:total().
            """,
        },
        {layer("src/core/price.erl", "src/adapters/store.erl"), purity("src/core/price.erl", "file")},
    ),
    "haskell": (
        {
            "architecture.toml": rules('"src/Shop/Core/**"', '"src/Shop/Adapters/**"'),
            "src/Shop/Core/Price.hs": """
                module Shop.Core.Price (total) where

                import Shop.Adapters.Store (save)
                import System.IO
                import qualified Data.Map as M
                {- import Shop.Adapters.Ghost -}

                total :: Int -> IO ()
                total _ = save
            """,
            "src/Shop/Adapters/Store.hs": """
                module Shop.Adapters.Store (save) where

                import Shop.Core.Price
            """,
        },
        {
            layer("src/Shop/Core/Price.hs", "src/Shop/Adapters/Store.hs"),
            purity("src/Shop/Core/Price.hs", "System.IO"),
            purity("src/Shop/Core/Price.hs", "IO"),
        },
    ),
    "purescript": (
        {
            "architecture.toml": rules('"src/Shop/Core/**"', '"src/Shop/Adapters/**"'),
            "src/Shop/Core/Price.purs": """
                module Shop.Core.Price where

                import Prelude
                import Shop.Adapters.Store (save)
                import Effect.Console (log)
            """,
            "src/Shop/Adapters/Store.purs": """
                module Shop.Adapters.Store where

                import Shop.Core.Price as Price
            """,
        },
        {layer("src/Shop/Core/Price.purs", "src/Shop/Adapters/Store.purs"), purity("src/Shop/Core/Price.purs", "Effect")},
    ),
    "elm": (
        {
            "architecture.toml": rules('"src/Core/**"', '"src/Adapters/**"'),
            "src/Core/Price.elm": """
                module Core.Price exposing (total)

                import Adapters.Store as Store
                import Http
                import Dict exposing (Dict)
            """,
            "src/Adapters/Store.elm": """
                port module Adapters.Store exposing (save)

                import Core.Price
            """,
        },
        {layer("src/Core/Price.elm", "src/Adapters/Store.elm"), purity("src/Core/Price.elm", "Http")},
    ),
    "ocaml": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "core/dune": "(library (name core))\n",
            "core/price.ml": """
                (* Ghost.save is only a comment *)
                let total () = Store.save (); print_endline "x"
                let size xs = List.length xs
            """,
            "adapters/dune": "(library (name adapters) (libraries core))\n",
            "adapters/store.ml": """
                let save () = Core.Price.total ()
            """,
        },
        {layer("core/price.ml", "adapters/store.ml"), purity("core/price.ml", "console")},
    ),
    "clojure": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "src/shop/core/price.clj": """
                (ns shop.core.price
                  "The price."
                  (:require [shop.adapters.store :as store :refer [save]]
                            [clojure.java.io :as io]
                            [clojure.string :as str])
                  (:import (java.util Date)))

                (defn total [] (println "x"))
            """,
            "src/shop/adapters/store.clj": """
                (ns shop.adapters.store
                  (:require shop.core.price))
            """,
        },
        {
            layer("src/shop/core/price.clj", "src/shop/adapters/store.clj"),
            purity("src/shop/core/price.clj", "clojure.java.io"),
            purity("src/shop/core/price.clj", "console"),
        },
    ),
    "lua": (
        {
            "architecture.toml": rules('"lua/shop/core/**"', '"lua/shop/adapters/**"'),
            "lua/shop/core/price.lua": """
                local store = require("shop.adapters.store")
                local socket = require "socket"
                --[[ require("shop.adapters.ghost") ]]
                print("x")
            """,
            "lua/shop/adapters/store.lua": """
                local price = require('shop.core.price')
            """,
            "lua/shop/adapters/init.lua": "return {}\n",
        },
        {
            layer("lua/shop/core/price.lua", "lua/shop/adapters/store.lua"),
            purity("lua/shop/core/price.lua", "socket"),
            purity("lua/shop/core/price.lua", "console"),
        },
    ),
    "perl": (
        {
            "architecture.toml": rules('"lib/Shop/Core/**"', '"lib/Shop/Adapters/**"'),
            "lib/Shop/Core/Price.pm": """
                package Shop::Core::Price;
                use strict;
                use warnings;
                use Shop::Adapters::Store;
                use File::Find;

                =pod

                use Shop::Adapters::Ghost;

                =cut

                1;
            """,
            "lib/Shop/Adapters/Store.pm": """
                package Shop::Adapters::Store;
                use parent 'Shop::Core::Price';
                1;
            """,
        },
        {layer("lib/Shop/Core/Price.pm", "lib/Shop/Adapters/Store.pm"), purity("lib/Shop/Core/Price.pm", "File")},
    ),
    "r": (
        {
            "architecture.toml": rules('"R/core/**"', '"R/adapters/**"'),
            "R/core/price.R": """
                source("R/adapters/store.R")
                library(httr)
                total <- function() Sys.time()
            """,
            "R/adapters/store.R": """
                source("R/core/price.R")
            """,
        },
        {layer("R/core/price.R", "R/adapters/store.R"), purity("R/core/price.R", "httr"), purity("R/core/price.R", "clock")},
    ),
    "julia": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.jl": """
                include("../adapters/store.jl")
                using Sockets, LinearAlgebra
                total() = println("x")
            """,
            "src/adapters/store.jl": """
                include("../core/price.jl")
            """,
        },
        {
            layer("src/core/price.jl", "src/adapters/store.jl"),
            purity("src/core/price.jl", "Sockets"),
            purity("src/core/price.jl", "console"),
        },
    ),
    "nim": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.nim": """
                import ../adapters/store
                import std/[os, strutils]
                echo "x"
            """,
            "src/adapters/store.nim": """
                import ../core/price, tables
            """,
        },
        {layer("src/core/price.nim", "src/adapters/store.nim"), purity("src/core/price.nim", "os"), purity("src/core/price.nim", "console")},
    ),
    "crystal": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.cr": """
                require "../adapters/store"
                require "http/client"
                puts "x"
            """,
            "src/adapters/store.cr": """
                require "../core/*"
            """,
        },
        {layer("src/core/price.cr", "src/adapters/store.cr"), purity("src/core/price.cr", "http"), purity("src/core/price.cr", "console")},
    ),
    "zig": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.zig": """
                const store = @import("../adapters/store.zig");
                const std = @import("std");
                pub fn total() void { std.debug.print("x", .{}); }
            """,
            "src/adapters/store.zig": """
                const price = @import("../core/price.zig");
            """,
        },
        {layer("src/core/price.zig", "src/adapters/store.zig"), purity("src/core/price.zig", "std.debug.print")},
    ),
    "v": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "v.mod": "Module { name: 'shop' }\n",
            "core/price.v": """
                module core

                import adapters
                import os

                fn total() { println('x') }
            """,
            "adapters/store.v": """
                module adapters

                import core
            """,
        },
        {layer("core/price.v", "adapters/store.v"), purity("core/price.v", "os"), purity("core/price.v", "console")},
    ),
    "odin": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "core/price.odin": """
                package core

                import "../adapters"
                import "core:os"
                import "core:fmt"

                total :: proc() { fmt.println("x") }
            """,
            "adapters/store.odin": """
                package adapters

                import price "../core"
            """,
        },
        {layer("core/price.odin", "adapters/store.odin"), purity("core/price.odin", "core:os"), purity("core/price.odin", "console")},
    ),
    "haxe": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "src/shop/core/Price.hx": """
                package shop.core;

                import shop.adapters.Store;
                import sys.io.File;

                class Price {}
            """,
            "src/shop/adapters/Store.hx": """
                package shop.adapters;

                import shop.core.Price;

                class Store {}
            """,
        },
        {layer("src/shop/core/Price.hx", "src/shop/adapters/Store.hx"), purity("src/shop/core/Price.hx", "sys")},
    ),
    "gleam": (
        {
            "architecture.toml": rules('"src/shop/core/**"', '"src/shop/adapters/**"'),
            "gleam.toml": 'name = "shop"\n',
            "src/shop/core/price.gleam": """
                import shop/adapters/store
                import gleam/io
                import gleam/list
            """,
            "src/shop/adapters/store.gleam": """
                import shop/core/price.{total}
            """,
        },
        {layer("src/shop/core/price.gleam", "src/shop/adapters/store.gleam"), purity("src/shop/core/price.gleam", "gleam/io")},
    ),
    "lean": (
        {
            "architecture.toml": rules('"Shop/Core/**"', '"Shop/Adapters/**"'),
            "lakefile.toml": 'name = "shop"\n',
            "Shop/Core/Price.lean": """
                import Shop.Adapters.Store
                import Mathlib.Data.Nat.Basic

                def main : IO Unit := pure ()
            """,
            "Shop/Adapters/Store.lean": """
                import Shop.Core.Price
            """,
        },
        {layer("Shop/Core/Price.lean", "Shop/Adapters/Store.lean"), purity("Shop/Core/Price.lean", "IO")},
    ),
    "racket": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "core/price.rkt": """
                #lang racket
                (require "../adapters/store.rkt"
                         racket/list
                         (prefix-in f: racket/file)
                         (only-in racket/string string-trim))
                (displayln "x")
            """,
            "adapters/store.rkt": """
                #lang racket
                (require (only-in "../core/price.rkt" total))
            """,
        },
        {layer("core/price.rkt", "adapters/store.rkt"), purity("core/price.rkt", "racket/file"), purity("core/price.rkt", "console")},
    ),
    "fortran": (
        {
            "architecture.toml": rules('"src/core/**"', '"src/adapters/**"'),
            "src/core/price.f90": """
                module price
                  use store
                  use mpi
                  use, intrinsic :: iso_fortran_env
                contains
                  subroutine total()
                    print *, "x"
                  end subroutine
                end module price
            """,
            "src/adapters/store.f90": """
                module store
                  USE Price
                end module store
            """,
        },
        {
            layer("src/core/price.f90", "src/adapters/store.f90"),
            purity("src/core/price.f90", "mpi"),
            purity("src/core/price.f90", "input/output"),
        },
    ),
    "nix": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "core/default.nix": """
                { ... }:
                {
                  imports = [ ../adapters/store.nix ];
                  # ../adapters/ghost.nix
                  note = "see ../adapters/other.nix";
                  now = builtins.currentTime;
                }
            """,
            "adapters/store.nix": """
                import ../core
            """,
            "adapters/other.nix": "{ }\n",
        },
        {layer("core/default.nix", "adapters/store.nix"), purity("core/default.nix", "builtins.currentTime")},
    ),
    "shell": (
        {
            "architecture.toml": rules('"core/**", "bin/**"', '"adapters/**"', pure=False),
            "core/price.sh": """
                #!/usr/bin/env bash
                . "$(dirname "$0")/../adapters/store.sh"
                source ./helpers.sh
                echo "$# arguments"  # source ../adapters/ghost.sh
            """,
            "core/helpers.sh": "true\n",
            "adapters/store.sh": """
                source "$ROOT/core/price.sh"
            """,
            "bin/run": """
                #!/bin/sh
                if true; then . adapters/store.sh; fi
            """,
            # A wrapper that starts a program it finds from its own location.
            "bin/report": """
                #!/usr/bin/env bash
                here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
                lib="$here/../adapters"
                exec python3 "$lib/report.py" "$@"  # not "$here/../adapters/ghost.py"
            """,
            "adapters/report.py": "x = 1\n",
            "adapters/ghost.py": "x = 1\n",
        },
        {
            layer("core/price.sh", "adapters/store.sh"),
            layer("bin/run", "adapters/store.sh"),
            layer("bin/report", "adapters/report.py"),
        },
    ),
    "powershell": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False, forbid=("Pester",)),
            "core/Price.ps1": """
                . "$PSScriptRoot\\..\\adapters\\Store.ps1"
                Import-Module Pester
            """,
            "adapters/Store.ps1": """
                . ./../core/Price.ps1
            """,
        },
        {layer("core/Price.ps1", "adapters/Store.ps1"), external("core/Price.ps1", "Pester")},
    ),
    "protobuf": (
        {
            "architecture.toml": rules('"proto/core/**"', '"proto/adapters/**"', pure=False, forbid=("google",)),
            "proto/core/price.proto": """
                syntax = "proto3";
                import "adapters/store.proto";
                import public "google/protobuf/timestamp.proto";
            """,
            "proto/adapters/store.proto": """
                syntax = "proto3";
                import "core/price.proto";
            """,
        },
        {layer("proto/core/price.proto", "proto/adapters/store.proto"), external("proto/core/price.proto", "google")},
    ),
    "graphql": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False),
            "core/price.graphql": """
                #import "../adapters/store.graphql"
                type Price { id: ID }
            """,
            "adapters/store.graphql": """
                # import Price from './../core/price.graphql'
                type Store { id: ID }
            """,
        },
        {layer("core/price.graphql", "adapters/store.graphql")},
    ),
    "solidity": (
        {
            "architecture.toml": rules('"contracts/core/**"', '"contracts/adapters/**"', forbid=("@openzeppelin/contracts",)),
            "contracts/core/Price.sol": """
                import "../adapters/Store.sol";
                import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

                contract Price { function at() public view returns (uint) { return block.timestamp; } }
            """,
            "contracts/adapters/Store.sol": """
                import {Price} from "contracts/core/Price.sol";
            """,
        },
        {
            layer("contracts/core/Price.sol", "contracts/adapters/Store.sol"),
            external("contracts/core/Price.sol", "@openzeppelin/contracts"),
            purity("contracts/core/Price.sol", "block"),
        },
    ),
    "terraform": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False, forbid=("terraform-aws-modules/vpc/aws",)),
            "core/main.tf": """
                module "store" {
                  source = "../adapters"
                }

                module "vpc" {
                  source = "terraform-aws-modules/vpc/aws"
                }
            """,
            "adapters/main.tf": """
                module "core" {
                  source = "../core"
                }
            """,
        },
        {layer("core/main.tf", "adapters/main.tf"), external("core/main.tf", "terraform-aws-modules/vpc/aws")},
    ),
    "qml": (
        {
            "architecture.toml": rules('"ui/core/**"', '"ui/adapters/**"'),
            "ui/core/qmldir": "module Shop.Core\nPrice 1.0 Price.qml\n",
            "ui/core/Price.qml": """
                import QtQuick 2.15
                import "../adapters"
                import QtNetwork

                Item { }
            """,
            "ui/adapters/Store.qml": """
                import QtQuick
                import "../core/Price.qml" as P
                import Shop.Core

                Item { }
            """,
        },
        {layer("ui/core/Price.qml", "ui/adapters/Store.qml"), purity("ui/core/Price.qml", "QtNetwork")},
    ),
    "typst": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False, forbid=("@preview/cetz",)),
            "core/price.typ": """
                #import "../adapters/store.typ": save
                #import "@preview/cetz:0.2.0"
            """,
            "adapters/store.typ": """
                #include "../core/price.typ"
            """,
        },
        {layer("core/price.typ", "adapters/store.typ"), external("core/price.typ", "@preview/cetz")},
    ),
    "latex": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False, forbid=("tikz",)),
            "core/price.tex": """
                \\usepackage{tikz, amsmath}
                \\input{../adapters/store}
                50\\% of it % \\input{../adapters/ghost}
            """,
            "adapters/store.tex": """
                \\include{../core/price}
            """,
            "adapters/ghost.tex": "x\n",
        },
        {layer("core/price.tex", "adapters/store.tex"), external("core/price.tex", "tikz")},
    ),
    "cue": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False, forbid=("strings",)),
            "cue.mod/module.cue": 'module: "example.com/shop"\n',
            "core/price.cue": """
                package core

                import (
                \t"example.com/shop/adapters"
                \t"strings"
                )
            """,
            "adapters/store.cue": """
                package adapters

                import "example.com/shop/core:core"
            """,
        },
        {layer("core/price.cue", "adapters/store.cue"), external("core/price.cue", "strings")},
    ),
    "dhall": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"'),
            "core/price.dhall": """
                let store = ../adapters/store.dhall
                let home = env:HOME as Text
                in  store
            """,
            "adapters/store.dhall": """
                let price = ../core/price
                in  price
            """,
        },
        {layer("core/price.dhall", "adapters/store.dhall"), purity("core/price.dhall", "environment")},
    ),
    "nickel": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False),
            "core/price.ncl": 'let store = import "../adapters/store.ncl" in store\n',
            "adapters/store.ncl": 'let price = import "../core/price.ncl" in price\n',
        },
        {layer("core/price.ncl", "adapters/store.ncl")},
    ),
    "rego": (
        {
            "architecture.toml": rules('"policy/core/**"', '"policy/adapters/**"'),
            "policy/core/price.rego": """
                package shop.core

                import data.shop.adapters
                import future.keywords.if

                allow if http.send({"method": "get"})
            """,
            "policy/adapters/store.rego": """
                package shop.adapters

                allow { data.shop.core.allow }
            """,
        },
        {layer("policy/core/price.rego", "policy/adapters/store.rego"), purity("policy/core/price.rego", "http.send")},
    ),
    "prolog": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', forbid=("http/http_open",)),
            "core/price.pl": """
                :- module(price, [total/1]).
                :- use_module('../adapters/store').
                :- use_module(library(http/http_open)).
                :- use_module(library(lists)).

                total(X) :- assertz(seen(X)).
            """,
            "adapters/store.pl": """
                :- module(store, []).
                :- use_module('../core/price').
            """,
        },
        {
            layer("core/price.pl", "adapters/store.pl"),
            external("core/price.pl", "http/http_open"),
            purity("core/price.pl", "assert"),
        },
    ),
    "verilog": (
        {
            "architecture.toml": rules('"rtl/core/**"', '"rtl/adapters/**"', pure=False),
            "rtl/core/price.v": """
                `include "../adapters/defs.vh"
                module price(input clk);
                  // ghost u_ghost (.clk(clk));
                  store #(.W(8)) u_store (.clk(clk));
                endmodule
            """,
            "rtl/adapters/defs.vh": "`define W 8\n",
            "rtl/adapters/store.v": """
                module store #(parameter W = 1) (input clk);
                  price u_price (.clk(clk));
                endmodule
            """,
        },
        {layer("rtl/core/price.v", "rtl/adapters/store.v"), layer("rtl/core/price.v", "rtl/adapters/defs.vh")},
    ),
    "vhdl": (
        {
            "architecture.toml": rules('"rtl/core/**"', '"rtl/adapters/**"', pure=False, forbid=("ieee",)),
            "rtl/core/price.vhd": """
                library ieee;
                use ieee.std_logic_1164.all;
                use work.store_pkg.all;

                entity price is
                end entity;
            """,
            "rtl/adapters/store_pkg.vhd": """
                package store_pkg is
                end package;
            """,
            "rtl/adapters/top.vhd": """
                entity top is
                end entity;

                architecture rtl of top is
                begin
                  u1: ENTITY work.Price port map (clk => clk);
                end architecture;
            """,
        },
        {layer("rtl/core/price.vhd", "rtl/adapters/store_pkg.vhd"), external("rtl/core/price.vhd", "ieee")},
    ),
    "assembly": (
        {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False),
            "core/price.asm": """
                %include "../adapters/store.inc"
                section .text
            """,
            "adapters/store.inc": """
                %include "../core/price.asm"
            """,
        },
        {layer("core/price.asm", "adapters/store.inc")},
    ),
}


class Languages(unittest.TestCase):
    def test_every_language_has_a_case(self):
        self.assertEqual(sorted(CASES), sorted(language.name for language in LANGUAGES))

    def test_each_language_reports_what_it_should_and_nothing_else(self):
        for name, (files, expected) in CASES.items():
            with self.subTest(language=name):
                self.assertEqual(found(tree(files)), expected)

    def test_the_command_lists_them(self):
        code, out = call("--languages")
        self.assertEqual(code, 0)
        listed = {line.split(":")[0] for line in out.splitlines()}
        self.assertEqual(listed, {name for name, _ in cli.languages()})
        self.assertIn("go: .go", out)
        self.assertIn("rust: .rs Cargo.toml", out)


class SharedExtensions(unittest.TestCase):
    def test_pl_is_perl_or_prolog_by_what_is_in_it(self):
        files = {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False),
            "core/run.pl": "use strict;\nuse warnings;\nrequire Shop::Store;\n",
            "adapters/Shop/Store.pm": "package Shop::Store;\n1;\n",
        }
        self.assertEqual(found(tree(files)), {layer("core/run.pl", "adapters/Shop/Store.pm")})

    def test_v_is_verilog_only_with_a_module_body(self):
        files = dict(CASES["v"][0])
        files["core/chip.v"] = "module chip(input clk);\n  import os;\nendmodule\n"
        self.assertEqual(found(tree(files)), CASES["v"][1])


class Roots(unittest.TestCase):
    def test_sources_roots_names_where_imports_start(self):
        files = {
            "architecture.toml": rules('"code/shop/core/**"', '"code/shop/adapters/**"', pure=False),
            "code/shop/core/price.lua": 'local store = require("shop.adapters.store")\n',
            "code/shop/adapters/store.lua": "return {}\n",
        }
        # Two segments match the end of a path; one segment needs a root.
        self.assertEqual(found(tree(files)), {layer("code/shop/core/price.lua", "code/shop/adapters/store.lua")})
        files["code/shop/core/price.lua"] = 'local shop = require("shop")\n'
        files["code/shop.lua"] = 'require("shop.adapters.store")\n'
        files["architecture.toml"] = rules('"code/shop/core/**"', '"code/shop/adapters/**", "code/shop.lua"', pure=False)
        self.assertEqual(found(tree(files)), set())
        files["architecture.toml"] += '\n[sources]\nroots = ["code"]\n'
        self.assertEqual(found(tree(files)), {layer("code/shop/core/price.lua", "code/shop.lua")})


class Notebooks(unittest.TestCase):
    def notebook(self, *cells: str, language: str = "python") -> str:
        return json.dumps(
            {
                "metadata": {"kernelspec": {"language": language}},
                "cells": [{"cell_type": "markdown", "source": "import os"}]
                + [{"cell_type": "code", "source": cell.splitlines(keepends=True)} for cell in cells],
            }
        )

    def files(self, notebook: str) -> dict[str, str]:
        return {
            "architecture.toml": rules('"notebooks/**"', '"shop/**"', pure=True),
            "shop/__init__.py": "",
            "shop/store.py": "x = 1\n",
            "notebooks/explore.ipynb": notebook,
        }

    def test_code_cells_are_read_as_python_and_the_line_is_the_cell(self):
        notebook = self.notebook("%matplotlib inline\nimport math\n", "from shop import store\n!ls\nimport subprocess\n")
        root = tree(self.files(notebook))
        self.assertEqual(
            found(root),
            {layer("notebooks/explore.ipynb", "shop/store.py"), purity("notebooks/explore.ipynb", "subprocess")},
        )
        self.assertIn("notebooks/explore.ipynb:3: layer:", run(root)[1])

    def test_a_notebook_in_another_language_is_left_alone(self):
        self.assertEqual(found(tree(self.files(self.notebook("library(httr)\n", language="R")))), set())

    def test_a_cell_that_is_not_python_fails_instead_of_passing_unchecked(self):
        self.assertEqual(
            found(tree(self.files(self.notebook("def broken(:\n")))),
            {("unreadable", "notebooks/explore.ipynb", "-")},
        )


class TestFiles(unittest.TestCase):
    def test_tests_are_skipped_unless_asked_for(self):
        files = dict(CASES["go"][0])
        files["core/price_test.go"] = 'package core\n\nimport "example.com/shop/adapters"\n'
        self.assertEqual(found(tree(files)), CASES["go"][1])
        files["architecture.toml"] = "include_tests = true\n" + files["architecture.toml"]
        self.assertEqual(found(tree(files)), CASES["go"][1] | {layer("core/price_test.go", "adapters/store.go")})


class NixStrings(unittest.TestCase):
    def test_escapes_do_not_end_a_string_and_code_in_one_is_read(self):
        nix = "\n".join(
            [
                "{ pkgs, ... }:",
                "{",
                "  # An escaped ${ inside an indented string, then text that looks like a lookup path.",
                "  environment.etc.\"kmscon.conf\".text = ''",
                "    dir=''${WILLEXANDER_HARNESS_DIR:-/run}",
                "    quote='''",
                "    grab-zoom-in=<Ctrl>plus",
                "    see ../scripts/ghost.sh",
                "  '';",
                "  script = \"run ${../scripts/recorder.py} \\\"<Alt>\\\"\";",
                "  text = builtins.readFile ../scripts/tmux.sh;",
                "}",
                "",
            ]
        )
        files = {
            "architecture.toml": rules('"modules/**"', '"scripts/**"'),
            "modules/consoles.nix": nix,
            "scripts/recorder.py": "x = 1\n",
            "scripts/tmux.sh": "true\n",
            "scripts/ghost.sh": "true\n",
        }
        self.assertEqual(
            found(tree(files)),
            {layer("modules/consoles.nix", "scripts/recorder.py"), layer("modules/consoles.nix", "scripts/tmux.sh")},
        )


class Heredocs(unittest.TestCase):
    def test_a_quote_in_a_here_document_does_not_hide_the_rest(self):
        script = "\n".join(
            [
                "cat <<EOF",
                "don't source ../adapters/ghost.sh",
                "EOF",
                "n=$(( 1 << shift ))",
                "source ../adapters/store.sh",
                "",
            ]
        )
        files = {
            "architecture.toml": rules('"core/**"', '"adapters/**"', pure=False),
            "core/run.sh": script,
            "adapters/store.sh": "true\n",
            "adapters/ghost.sh": "true\n",
        }
        self.assertEqual(found(tree(files)), {layer("core/run.sh", "adapters/store.sh")})


class NixDirectories(unittest.TestCase):
    def test_a_path_to_a_directory_uses_what_is_in_it(self):
        files = {
            "architecture.toml": rules('"packages/**"', '"sources/**"', pure=False),
            "packages/app.nix": "{ stdenv }:\nstdenv.mkDerivation {\n  src = ../sources/app;\n  all = ./.;\n  up = ../.;\n}\n",
            "sources/app/main.c": "int main(void) { return 0; }\n",
        }
        self.assertEqual(found(tree(files)), {layer("packages/app.nix", "sources/app/main.c")})


class Scripts(unittest.TestCase):
    def test_a_script_without_an_extension_is_read_as_its_first_line_says(self):
        files = {
            "architecture.toml": rules('"bin/**"', '"lib/**"'),
            "lib/store.py": "x = 1\n",
            "lib/store.rb": "X = 1\n",
            "bin/report": "#!/usr/bin/env python3\nimport subprocess\nfrom lib import store\n",
            "bin/sync": '#!/usr/bin/env ruby\nrequire_relative "../lib/store"\n',
            "bin/notes": "import os\n",
        }
        self.assertEqual(
            found(tree(files)),
            {layer("bin/report", "lib/store.py"), purity("bin/report", "subprocess"), layer("bin/sync", "lib/store.rb")},
        )


class Blanking(unittest.TestCase):
    def test_comments_and_string_contents_become_spaces_and_positions_stay(self):
        text = 'a = "x // y" // gone\n/* b\n c */ d = \'q\'\n'
        bare = blank(text, Syntax(quotes="\"'"))
        self.assertEqual(bare, 'a = "      "        \n    \n      d = \' \'\n')
        self.assertEqual(len(bare), len(text))

    def test_nested_comments_and_triple_quotes(self):
        text = '{- a {- b -} c -} x = """ -- no """ -- yes\n'
        bare = blank(text, Syntax(line=("--",), block=(("{-", "-}"),), nested=True, quotes='"', triple=True))
        self.assertEqual(bare.strip(), 'x = """       """')

    def test_a_hash_inside_a_word_is_not_a_comment(self):
        bare = blank('echo "$#" ${#x} # gone\n', Syntax(line=("#",), block=(), quotes="\"'", spaced=True))
        self.assertEqual(bare, 'echo "  " ${#x}       \n')


if __name__ == "__main__":
    unittest.main()
