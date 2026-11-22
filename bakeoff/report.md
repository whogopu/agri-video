# Image model bake-off

Updated 2026-11-22 10:50. Pass = pass or minor.

| model | images | Claude pass | user pass | median s/img | peak GB |
|---|---|---|---|---|---|
| klein4b_q4 | 12 | 5/12 | 6/12 | 20.9 | 6.56 |
| klein_base4b_q8 | 3 | 1/3 | - | 1139.6 | 10.62 |
| zimage_q8 | 1 | 1/1 | - | 1749.1 | 14.0 |
| zimage_q6 | 12 | 10/12 | 10/12 | 819.0 | 7.73 |
| zimage_turbo_q6 | 1 | 0/1 | - | 71.1 | 7.4 |
| flux3_klein_q8 | 39 | 35/39 | 35/39 | 121.0 | 7.79 |
| flux3_klein_q8_cast | 18 | 15/18 | 15/18 | 189 | 8.96 |
| flux3_klein_base_q8 | 36 | 32/36 | 33/36 | 713.1 | 11.19 |
| ernie_q6 | 1 | 0/1 | - | 2213.1 | 10.25 |
| krea2_turbo_q5 | 1 | 0/1 | - | 418.2 | 17.85 |
| qwen2512_q4 | 1 | 0/1 | - | 5246.3 | 28.0 |
