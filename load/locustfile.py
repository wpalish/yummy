from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


class CatalogUser(HttpUser):
    wait_time = between(0.2, 1.0)

    @task(6)
    def catalog(self):
        with self.client.get("/boxes", name="GET /boxes", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"status {response.status_code}")

    @task(2)
    def districts(self):
        self.client.get("/districts", name="GET /districts")

    @task(1)
    def random_box(self):
        boxes = self.client.get("/boxes", name="GET /boxes [select]")
        if boxes.status_code == 200 and boxes.json():
            box = random.choice(boxes.json())
            self.client.get(f"/boxes/{box['id']}", name="GET /boxes/:id")


class AuthenticatedCustomer(HttpUser):
    wait_time = between(0.5, 2.0)
    token = os.getenv("CUSTOMER_BEARER_TOKEN", "")

    def on_start(self):
        if self.token:
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    @task
    def orders(self):
        if self.token:
            self.client.get("/me/orders", name="GET /me/orders")
        else:
            self.client.get("/boxes", name="GET /boxes [anonymous]")
