# Proto codegen. Requires: buf, protoc-gen-go, protoc-gen-go-grpc on PATH
# (go install ...). Python target uses grpcio-tools (bundled protoc) from the
# worker's uv env — run via `make gen-py` after `uv sync` in cosign-worker.
PY_OUT := ../../services/cosign-worker/cosign_worker/rpc/pb

.PHONY: gen gen-go gen-py lint
gen: gen-go gen-py

gen-go:
	buf generate

lint:
	buf lint

gen-py:
	mkdir -p $(PY_OUT)
	cd ../../services/cosign-worker && \
	  uv run python -m grpc_tools.protoc \
	    -I ../../libs/proto \
	    --python_out=cosign_worker/rpc/pb \
	    --grpc_python_out=cosign_worker/rpc/pb \
	    --pyi_out=cosign_worker/rpc/pb \
	    ../../libs/proto/orchestration.proto
	@echo "Generated Python stubs into $(PY_OUT) (fix imports if needed)"
