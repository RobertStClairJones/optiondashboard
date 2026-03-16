.PHONY: run install

run:
	streamlit run dashboard.py

install:
	pip install -r requirements.txt
