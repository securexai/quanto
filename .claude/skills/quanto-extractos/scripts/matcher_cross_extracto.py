#!/usr/bin/env python3
import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ahorros", required=True)
    parser.add_argument("--tc-davivienda", required=True)
    parser.add_argument("--tc-davibank", required=True)
    parser.add_argument("--nequi", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
