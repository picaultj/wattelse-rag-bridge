#!/bin/bash
#
# Copyright (c) 2026, RTE (https://www.rte-france.com)
# See AUTHORS.txt
# SPDX-License-Identifier: MPL-2.0
# This file is part of datagrid-mcp.
#

echo
echo "This script starts the MCP server"
echo

uv run python wattelse_mcp/server.py
