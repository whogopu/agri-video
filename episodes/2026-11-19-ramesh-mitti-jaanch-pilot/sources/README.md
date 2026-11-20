# Sources — 2026-11-19-mitti-ki-jaanch

Fetched 2026-11-19. `.txt` files are text extracted from the originals (for searching); cite the original.

| File | Title | Publisher | URL |
|---|---|---|---|
| `shc-faq-english.pdf` (+ .txt) | Soil Health Card — FAQ (Annexure I) | Dept. of Agriculture & Cooperation, Ministry of Agriculture, GoI (2015 scheme FAQ; copy hosted by SVNIT Unnat Bharat) | https://www.svnit.ac.in/Unnat_Bharat/PI/pdf/Agriculture%20&%20Organic%20Farming/Schemes%20by%20Government%20of%20India/Soil%20Health%20Card/Annexure%20I%20FAQ_Final_English.pdf |
| `pib-shc-factsheet-2025-08.pdf` (+ .txt) | Soil Health Card Scheme factsheet (Aug 2025) | Press Information Bureau, GoI | https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/aug/doc2025816613501.pdf |
| `pib-shc-factsheet.html` (+ .txt) | Factsheet — Soil Health Card Scheme (older, cites 2017 NPC study) | Press Information Bureau, GoI | https://www.pib.gov.in/FactsheetDetails.aspx?Id=148602 |
| `icar-ccari-soil-sampling.html` (+ .txt) | How to take soil sample | ICAR – Central Coastal Agricultural Research Institute, Goa | https://ccari.res.in/soilgoa/soilsample.php |
| `hp-agriculture-shc.txt` | Soil Health Card (state page) | Department of Agriculture, Himachal Pradesh | https://agriculture.hp.gov.in/?p=1654 |
| `user-research-notes.md` | User's research notes | — (lead only, not cited) | — |

Not usable: soilhealth.dac.gov.in/support and myscheme.gov.in/schemes/rkvyshfshc are JavaScript apps; plain download returned no content.

## Conflicts found
- Cost per sample: user notes say ₹300; Ministry FAQ and PIB 2025 say **₹190** per sample (paid by the central government to states). Script avoids the number.
- Card frequency: PIB 2025 says "once every 3 years" and also "every 2 years" (objectives). Ministry FAQ: "once in a cycle of 3 years". Script uses the 3-year cycle.
- Spots per field: ICAR-CCARI says 10–15 zig-zag spots (farmer self-sampling); the SHC FAQ describes four corners + centre (by trained staff on a 2.5 ha grid). Script uses ICAR for self-sampling.
- "20–30 days before sowing" and "30 days after fertilizer" (user notes): not found in any fetched official source → not used.
- "Testing is free for farmers": stated by the HP state department; central documents say the government pays the cost per sample. Script says "the government bears the testing cost".
