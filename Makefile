.PHONY: test generate all

test:
	python3 -m pytest test_generate.py -v

generate:
	python3 generate.py

all: test generate
