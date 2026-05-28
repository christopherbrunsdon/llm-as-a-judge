#!/bin/sh

lsof -ti :7777 | xargs kill 2>/dev/null && echo "killed" || echo "nothing on 7777"


