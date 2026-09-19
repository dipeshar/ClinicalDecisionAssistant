# Writing a case

Copy `TEMPLATE.md` and fill it in. Rules:

1. Use exactly the 8 `##` headings in the template, in that order.
2. Text before the first `##` is not a section and cannot be cited.
3. Keep each section short. Agents cite quotes of 4 to 40 words, so write clear, quotable sentences.
4. A missing heading is recorded as missing, not ignored.
5. Do not use HTML comments or hidden text in a real case. The scanner flags them.
6. Synthetic data only. No real patient data and no real clinician names.

Files in this folder:

- `original/`: the sample case provided with the brief, untouched.
- `cardiac_01.md`: the sample case converted by hand into our template.
- `contrast_02.md`: a contrasting case where the answer should be "delay" or "decline".
- `cardiac_01_injection.md`: case 1 with a hidden instruction, to test the injection defense.
- `script_03.md`: a case with a `<script>` line, to test that the report page shows text as text.
