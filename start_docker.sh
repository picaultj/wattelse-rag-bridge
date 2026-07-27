#
# Copyright (c) 2026, RTE (https://www.rte-france.com)
# See AUTHORS.txt
# SPDX-License-Identifier: MPL-2.0
# This file is part of datagrid-mcp.
#
source .venv/bin/activate

git pull

docker compose down
docker compose up --build -d
