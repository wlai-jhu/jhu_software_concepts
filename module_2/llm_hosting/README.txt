Add the assignment-provided local LLM hosting zip contents in this folder.

Expected workflow after adding the provided files:
1. cd module_2/llm_hosting
2. pip install -r requirements.txt
3. python app.py --file ../data/llm_input.json --out ../data/llm_output.jsonl
4. Use ../llm_clean.py from the module_2 folder to merge standardized fields into
   ../llm_extend_applicant_data.json while preserving original raw fields.
