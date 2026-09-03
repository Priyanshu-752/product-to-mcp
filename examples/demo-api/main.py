from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Product-to-MCP Demo API", version="1.0.0")
PRODUCTS = [{"id": "p-1", "name": "Starter plan", "price": 29}]


class ProductInput(BaseModel):
    id: str
    name: str
    price: float


class ProductPatch(BaseModel):
    name: str | None = None
    price: float | None = None


@app.get("/products")
def list_products(limit: int = 20):
    return {"items": PRODUCTS[:limit], "count": len(PRODUCTS[:limit])}


@app.get("/products/{product_id}")
def get_product(product_id: str):
    return next((item for item in PRODUCTS if item["id"] == product_id), {"error": "not_found"})


@app.post("/products", status_code=201)
def create_product(product: ProductInput):
    if any(item["id"] == product.id for item in PRODUCTS):
        raise HTTPException(status_code=409, detail="product_already_exists")
    value = product.model_dump()
    PRODUCTS.append(value)
    return value


@app.put("/products/{product_id}")
def replace_product(product_id: str, product: ProductInput):
    for index, item in enumerate(PRODUCTS):
        if item["id"] == product_id:
            value = product.model_dump()
            PRODUCTS[index] = value
            return value
    raise HTTPException(status_code=404, detail="product_not_found")


@app.patch("/products/{product_id}")
def update_product(product_id: str, patch: ProductPatch):
    for item in PRODUCTS:
        if item["id"] == product_id:
            updates = patch.model_dump(exclude_none=True)
            item.update(updates)
            return item
    raise HTTPException(status_code=404, detail="product_not_found")


@app.delete("/products/{product_id}")
def delete_product(product_id: str):
    for index, item in enumerate(PRODUCTS):
        if item["id"] == product_id:
            return PRODUCTS.pop(index)
    raise HTTPException(status_code=404, detail="product_not_found")
