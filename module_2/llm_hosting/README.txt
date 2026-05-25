Add the assignment-provided local LLM hosting zip contents in this folder.

Expected workflow after adding the provided files:
1. cd module_2/llm_hosting
2. pip install -r requirements.txt
3. python app.py --file ../data/raw_applicant_data.json > ../data/llm_standardized.json
4. Merge standardized fields into ../applicant_data.json while preserving original raw fields.
