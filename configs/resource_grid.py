# -*- coding: utf-8 -*-
# filename: configs/resource_grid.py
import asyncio

SEMAPHORES = {
    "STRATEGIC": asyncio.Semaphore(2),
    "ENGINEERING": asyncio.Semaphore(5),
    "BASE": asyncio.Semaphore(10)
}
TIMEOUTS = {
    "STRATEGIC": 240,
    "ENGINEERING": 150,
    "BASE": 120,
    "REVIEWER": 300
}