#!/usr/bin/env python3
"""Build the personal website from researchmap data.

Usage:
    python3 build.py            # fetch the latest data from researchmap and rebuild
    python3 build.py --offline  # rebuild from the cached data in data/researchmap/

Career, education, grants, awards, papers and book chapters are pulled from
researchmap (https://researchmap.jp/sansai). Hand-written text (contact,
research summary, resources) lives in the CONTENT dict below.
"""
import base64
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "researchmap"
PERMALINK = "sansai"
API = f"https://api.researchmap.jp/{PERMALINK}"
SECTIONS = [
    "profile", "research_experience", "education", "research_projects", "awards",
    "published_papers", "books_etc", "research_interests", "association_memberships",
]

# Paper records on researchmap that should not appear on the site
# (preprints are dropped automatically; list rm:id values here to hide others).
EXCLUDE_PAPER_IDS = set()
EXCLUDE_TITLE_PATTERNS = [
    r"^Correction:",
    r"^CT Image-Based Biopsy",  # imported by ORCID, appears to be a different author
]
JOURNAL_FIX = {
    "Developmetal Biology": "Developmental Biology",
    "Bio-protocol,": "Bio-protocol",
    "G3 (Bethesda, Md.)": "G3: Genes, Genomes, Genetics",
    "G3 (Bethesda)": "G3: Genes, Genomes, Genetics",
    "Genesis (New York, N.Y. : 2000)": "Genesis",
    "Methods in Molecular Biology (Clifton, N.J.)": "Methods in Molecular Biology",
    "The Journal of Experimental Biology": "Journal of Experimental Biology",
    "Philosophical Transactions of the Royal Society of London. Series B, Biological sciences":
        "Philosophical Transactions of the Royal Society B",
    "Proceedings of the National Academy of Sciences of the United States of America":
        "Proceedings of the National Academy of Sciences USA",
}

# Volume, pages and year come from Crossref (via each paper's DOI); whether a
# paper is a review comes from PubMed's publication type. Override either here.
DOI_META = ROOT / "data" / "doi_metadata.json"
# Corresponding (*) and equal-contribution (†) authors, keyed by DOI.
# Edit data/author_roles.json by hand: {"<doi>": {"corresponding": [names], "equal": [names]}}
AUTHOR_ROLES = ROOT / "data" / "author_roles.json"
REVIEW_OVERRIDE = {
    "10.1098/rsbl.2021.0212": False,  # Mesozoic origin ... ricefishes: research article
}

# --------------------------------------------------------------------------
# Hand-written content
# --------------------------------------------------------------------------
LINKS = [
    ("researchmap", "https://researchmap.jp/sansai"),
    ("ORCID", "https://orcid.org/0000-0003-2683-0160"),
    ("Google Scholar", "https://scholar.google.co.jp/citations?user=vPIOMUEAAAAJ"),
    ("PubMed", "https://pubmed.ncbi.nlm.nih.gov/?term=Ansai+S%5BAuthor%5D"),
]

CONTENT = {
    "ja": {
        "name": "安齋 賢",
        "name_sub": "Satoshi Ansai, Ph.D.",
        "title": "教授",
        "affiliation": [
            "岡山大学 理学部附属臨海実験所",
            "学術研究院 環境生命自然科学学域（理）",
        ],
        "address": "〒701-4303 岡山県瀬戸内市牛窓町鹿忍130-17",
        "tel": "0869-34-5210",
        "email": "ansai@okayama-u.ac.jp",
        "intro": "真骨魚類、特に東・東南アジアで著しく多様化したメダカ科魚類を主なモデルとして、"
                 "表現型の多様性を生み出すゲノム領域や遺伝子を、集団ゲノム解析とゲノム編集を組み合わせて研究しています。",
        "nav": {"index": "Top", "profile": "Profile", "research": "Research",
                "publications": "Publications", "resources": "Resources"},
        "h": {
            "interests": "研究キーワード", "recent": "最近の論文", "all_pubs": "すべての論文を見る →",
            "career": "職歴", "education": "学歴", "degree": "学位", "grants": "研究費",
            "awards": "受賞", "societies": "所属学会", "courses": "トレーニングコース講師",
            "papers": "原著論文", "reviews": "総説", "marks": "* 責任著者　† 同等貢献", "chapters": "著書（分担執筆）", "contact": "連絡先",
            "pi": "研究代表者", "co": "研究分担者", "kaken": "科研費", "other": "その他の研究費", "present": "現在",
            "updated": "業績・経歴は researchmap の情報から自動生成しています。",
        },
        "research_title": "魚類の多様性を生み出す分子基盤の解明",
        "research_lead": "真骨魚類は、脊椎動物の中でも最も多くの種数を含む分類群で、海水〜淡水域の様々な環境に適応し、"
                         "急速な多様化を遂げています。その表現型多様性を生み出す進化メカニズムの解明に向け、"
                         "東・東南アジアにおいて著しく多様化したメダカ科魚類を主なモデルとし、ゲノム解析や遺伝学的解析を駆使して、"
                         "その原因となるゲノム領域・遺伝子を解析しています。また最先端のゲノム編集技術を適用し、"
                         "同定した分子・領域の機能解析を進めています。さらに、同様の手法を多様な水圏動物に適用し、"
                         "より広い時間スケールの進化現象の理解や水産育種に活用する試みも進めています。",
        "research": [
            ("性淘汰による性的二型の多様化",
             "雌雄で顕著に表現型が異なる形質（性的二型）は、広く様々な生物に見られますが、その対象となる表現型は急速に多様化します。"
             "これらは、配偶者選択や雄間闘争など、繁殖をめぐる競争を通じて働く性淘汰を通じて進化してきたと考えられています。"
             "本研究室では、メダカ科魚類において観察される多様な性的二型について、それらを制御する遺伝子をゲノム解析で探索し、"
             "ゲノム編集による機能解析と行動実験を組み合わせて、表現型の進化と性淘汰との関係を調べています。"),
            ("核型進化と種分化・生殖隔離",
             "染色体の数やかたち（＝核型）の種間多様性は、古典的な細胞遺伝学研究により広く観察されていますが、"
             "その進化的意義には未解明な点が多く残されています。核型の変化は、雑種における正常な細胞分裂を妨げることで"
             "生殖隔離の原因となり、種分化をもたらすと考えられますが、直接的な検証例は限られています。"
             "本研究室では、メダカ科内で観察される核型の多様性をモデルとして、ゲノム解析と実験の両面から、"
             "染色体の再編成がどのように生じ、生殖隔離や種分化にどう寄与するのかを明らかにします。"),
            ("性染色体の転換と性決定システムの多様性",
             "近年の研究から、真骨魚類では近縁種間でも性決定遺伝子や性染色体が繰り返し入れ替わることが明らかになっています。"
             "メダカ科魚類をモデルとして、新しい性決定遺伝子がどのように獲得され、性染色体がどのように分化していくのか、"
             "また性決定システムの違いが交雑や種分化に与える影響を研究しています。"
             "また同様の解析を水産重要種を含む、真骨魚類の様々な種に適用して、性染色体の多様性をもたらす進化的要因の解明を目指しています。"),
            ("魚類における遺伝子改変技術の高度化",
             "本研究室では、ゲノム編集技術をメダカでいち早く導入するなど、遺伝子改変技術の開発に取り組んできました。"
             "CRISPR/Cas システムを用いたノックイン法やトランスポゾンを利用した遺伝子導入法など、より効率の高い手法の開発を続けるとともに、"
             "それらを利用した神経科学ツールの導入など、幅広い基礎研究に利用可能な研究リソースの開発を行っています。"
             "また、これらの技術の他種への導入も積極的に行い、多様な種での遺伝子機能解析を可能にする技術基盤の確立を目指しています。"),
            ("進化ゲノミクスに基づく水産有用形質の遺伝基盤の解明",
             "進化生物学分野で発展が進むゲノム情報解析技術は、養殖魚を中心とした水産有用種の育種にも応用できます。"
             "特に、性統御や成長等の有用形質に関わる遺伝子や変異をゲノム解析で特定し、"
             "有用系統の育種を推進するための解析基盤構築を進めています。"),
        ],
    },
    "en": {
        "name": "Satoshi Ansai, Ph.D.",
        "name_sub": "安齋 賢",
        "title": "Professor",
        "affiliation": [
            "Ushimado Marine Institute, Faculty of Science, Okayama University",
        ],
        "address": "130-17 Kashino, Ushimado, Setouchi, Okayama 701-4303, Japan",
        "tel": "+81-869-34-5210",
        "email": "ansai@okayama-u.ac.jp",
        "intro": "Using ricefishes (Adrianichthyidae), a family that has diversified remarkably across "
                 "East and Southeast Asia, as the main model, I combine population genomics with genome "
                 "editing to identify the genomic regions and genes behind phenotypic diversity in teleosts.",
        "nav": {"index": "Top", "profile": "Profile", "research": "Research",
                "publications": "Publications", "resources": "Resources"},
        "h": {
            "interests": "Research keywords", "recent": "Recent publications", "all_pubs": "All publications →",
            "career": "Appointments", "education": "Education", "degree": "Degree", "grants": "Grants",
            "awards": "Awards", "societies": "Memberships", "courses": "Training courses (staff)",
            "papers": "Original articles", "reviews": "Reviews", "marks": "* Corresponding author　† Equal contribution", "chapters": "Book chapters", "contact": "Contact",
            "pi": "Principal investigator", "co": "Co-investigator", "kaken": "JSPS KAKENHI", "other": "Other grants", "present": "present",
            "updated": "Career and publication lists are generated from researchmap.",
        },
        "research_title": "Molecular basis of diversity in fishes",
        "research_lead": "Teleosts are the most species-rich group of vertebrates, having adapted to environments "
                         "from seawater to freshwater and diversified rapidly. To understand the evolutionary "
                         "mechanisms behind their phenotypic diversity, I use ricefishes (Adrianichthyidae), a "
                         "family that has diversified remarkably across East and Southeast Asia, as the main "
                         "model, and apply genomic and genetic analyses to identify the responsible genomic "
                         "regions and genes. State-of-the-art genome editing is then used to test the function "
                         "of the molecules and regions identified. The same approaches are also being extended "
                         "to a wider range of aquatic animals, both to study evolution over broader timescales "
                         "and to support breeding of aquaculture species.",
        "research": [
            ("Diversification of sexual dimorphism under sexual selection",
             "Traits that differ markedly between the sexes are found across a wide range of organisms, and the "
             "traits involved diversify rapidly. They are thought to have evolved under sexual selection, which "
             "acts through competition over reproduction such as mate choice and male–male competition. For the "
             "diverse sexually dimorphic traits seen in ricefishes, we search for the controlling genes by "
             "genomic analysis and combine genome editing with behavioral assays to examine how phenotypic "
             "evolution relates to sexual selection."),
            ("Karyotype evolution, speciation and reproductive isolation",
             "Differences between species in chromosome number and shape (karyotype) have long been documented "
             "by classical cytogenetics, yet their evolutionary significance remains largely unresolved. Changes "
             "in karyotype are thought to cause reproductive isolation by disrupting normal cell division in "
             "hybrids, and thus to drive speciation, but direct tests are scarce. Using the karyotypic diversity "
             "within ricefishes as a model, we combine genomic analysis with experiments to reveal how "
             "chromosomal rearrangements arise and how they contribute to reproductive isolation and speciation."),
            ("Sex chromosome turnover and the diversity of sex-determination systems",
             "Recent work has shown that sex-determining genes and sex chromosomes turn over repeatedly in "
             "teleosts, even among closely related species. Using ricefishes as a model, we study how new "
             "sex-determining genes are acquired, how sex chromosomes differentiate, and how differences in "
             "sex-determination systems affect hybridization and speciation. We also extend the same analyses to "
             "a range of teleosts, including commercially important species, to identify the evolutionary forces "
             "that generate the diversity of sex chromosomes."),
            ("Advancing genetic modification technologies in fish",
             "We have worked on genetic modification technologies, including the early adoption of genome "
             "editing in medaka. Alongside continued development of more efficient methods, such as knock-in "
             "with the CRISPR/Cas system and transposon-mediated transgenesis, we build research resources for "
             "broad use in basic research, for example by introducing neuroscience tools. We also actively "
             "transfer these technologies to other species, aiming to establish a technical basis for analyzing "
             "gene function across diverse species."),
            ("Genetic basis of aquaculture traits through evolutionary genomics",
             "The genomic analysis methods advancing in evolutionary biology can also be applied to breeding "
             "commercially important aquatic species, aquaculture fishes in particular. We identify genes and "
             "variants underlying useful traits such as sex control and growth, and build the analytical "
             "resources needed to advance the breeding of improved strains."),
        ],
    },
}

RESEARCH_REFS = [[('Ansai et al., Nature Communications (2021)', '10.1038/s41467-021-21697-0'), ('Ogino et al., Nature Communications (2023)', '10.1038/s41467-023-37026-6'), ('Ueda et al., Biology Letters (2024)', '10.1098/rsbl.2024.0159')], [('Ansai et al., Molecular Ecology (2024)', '10.1111/mec.17222'), ('Ansai &amp; Kitano, Philosophical Transactions of the Royal Society B (2022)', '10.1098/rstb.2020.0516')], [('Ansai et al., Journal of Evolutionary Biology (2022)', '10.1111/jeb.14076'), ('Kitano et al., The American Naturalist (2023)', '10.1086/724840'), ('Kitano et al., Annual Review of Animal Biosciences (2024)', '10.1146/annurev-animal-021122-113935')], [('Ansai &amp; Kinoshita, Biology Open (2014)', '10.1242/bio.20148177'), ('Tanaka et al., Transgenic Research (2025)', '10.1007/s11248-025-00466-5'), ('Seki et al., Neuroscience Research (2025)', '10.1016/j.neures.2025.104944')], []]


COURSES = {
    "ja": [
        "The 10th NIBB International Practical Course “Genome Editing and Imaging of Fish and Amphibians”, 2018年9月, 基礎生物学研究所",
        "The 9th NIBB International Practical Course “Genetics and Imaging of Medaka and Zebrafish”, 2016年8月, 基礎生物学研究所",
        "2015 メダカベーシックトレーニングコース, 2015年8月, 基礎生物学研究所",
        "The 8th NIBB International Practical Course “Experimental Techniques using Medaka and Xenopus”, 2014年9月, 基礎生物学研究所",
        "人工ヌクレアーゼによる小型魚類の遺伝子破壊法（TALEN講習会）, 2013年2月, 基礎生物学研究所",
    ],
    "en": [
        "The 10th NIBB International Practical Course “Genome Editing and Imaging of Fish and Amphibians”, Sep 2018, NIBB, Okazaki",
        "The 9th NIBB International Practical Course “Genetics and Imaging of Medaka and Zebrafish”, Aug 2016, NIBB, Okazaki",
        "2015 Medaka Basic Training Course (in Japanese), Aug 2015, NIBB, Okazaki",
        "The 8th NIBB International Practical Course “Experimental Techniques using Medaka and Xenopus”, Sep 2014, NIBB, Okazaki",
        "TALEN training course for small laboratory fish (in Japanese), Feb 2013, NIBB, Okazaki",
    ],
}

RESOURCES = {
    "ja": """
<section>
  <h2>プロトコル</h2>
  <ul class="res">
    <li><a href="{p}files/CRISPRv3_jp.pdf">CRISPR/Cas9 Protocol v3.0</a> <span class="meta">日本語 · PDF 247KB</span>
      <p>完全にプラスミドフリーで sgRNA を合成できるプロトコルです。RNA 合成に使用する試薬等も変更しています。</p></li>
    <li><a href="{p}files/CRISPR_jp.pdf">CRISPR/Cas9 Protocol v1.4.1</a> <span class="meta">日本語 · PDF 166KB · <a href="https://doi.org/10.1242/bio.20148177">Ansai &amp; Kinoshita, 2014</a></span>
      <p>オリゴヌクレオチドのクローニングによって sgRNA を作製する旧プロトコルです。</p></li>
    <li><a href="{p}files/CRISPR_en.pdf">CRISPR/Cas9 Protocol</a> <span class="meta">英語 · PDF 1.5MB · <a href="https://doi.org/10.1242/bio.20148177">Ansai &amp; Kinoshita, 2014</a>; <a href="https://doi.org/10.1111/dgd.12104">Ansai et al., 2014</a> (HMA)</span>
      <p>英語版プロトコルです。変異検出法についても詳しく記載しています。</p></li>
    <li><a href="{p}files/TALEN_protocol.pdf">TALEN Protocol v1.0</a> <span class="meta">日本語 · PDF 1.8MB · <a href="https://doi.org/10.1534/genetics.112.147645">Ansai et al., 2013</a></span>
      <p>2013年以降更新していないため、変異検出など一部の情報は古くなっています。</p></li>
  </ul>
</section>
<section>
  <h2>sgRNA 設計用ファイル</h2>
  <ul class="res">
    <li><a href="{p}files/sgRNA_PCRoligo.xlsx">sgRNA_PCRoligo.xlsx</a> <span class="meta">Excel · 10KB</span>
      <p>PCR によるテンプレート合成（v3.0 等）用の sgRNA オリゴ設計支援シートです。</p></li>
    <li><a href="{p}files/sgRNA_design.xls">sgRNA_design.xls</a> <span class="meta">Excel · 35KB</span> /
        <a href="{p}files/sgRNA_design.ods">sgRNA_design.ods</a> <span class="meta">OpenOffice · 22KB</span>
      <p>pDR274 クローニング用のオリゴ設計支援ツール（マクロ使用）です。</p></li>
  </ul>
</section>
<section>
  <h2>ベクター</h2>
  <ul class="res">
    <li><strong>pCS2+hSpCas9</strong> <span class="meta"><a href="{p}files/pCS2+hSpCas9.pdf">Map (PDF)</a> · <a href="{p}files/pCS2+hSpCas9.gb">Sequence (GenBank)</a> · <a href="https://www.addgene.org/51815/">Addgene #51815</a></span>
      <p>ヒトコドン最適化 SpCas9 を pCS2+ にクローニングした Cas9 mRNA 合成用ベクター（SP6）です。
      メダカやゼブラフィッシュ、各種養殖魚等の真骨魚類を中心に、無顎類や両生類胚での実績もあり、水生動物の受精卵で高効率に働きます。<br>原著論文: <a href="https://doi.org/10.1242/bio.20148177"><em>Ansai &amp; Kinoshita, 2014</em></a></p></li>
    <li><strong>pUC-BaitD-Xhbb-EGFP</strong> <span class="meta"><a href="https://github.com/satoshi-ansai/Plasmids/blob/main/NHEJ_KI/pUC-BaitD-Xhbb-EGFP.gb">Sequence (GenBank)</a> · <a href="https://github.com/satoshi-ansai/Plasmids">GitHub: Plasmids</a></span>
      <p>NHEJ を利用した Cas9 ノックイン用のドナーベクターです。
      ツメガエル beta-globin 遺伝子由来の最小プロモーターを使っており、バックグラウンドが低く抑えられます。<br>原著論文: <a href="https://doi.org/10.1002/dvg.23519"><em>Kayo et al., 2023</em></a></p></li>
    <li><strong>Tip100 トランスポゾン用ベクター</strong> <span class="meta"><a href="https://www.nibb.ac.jp/hoshino/Tip100_vector_for_Medaka.html">配列・分譲（基礎生物学研究所 星野研究室）</a></span>
      <p>アサガオ由来の DNA 型トランスポゾン Tip100 を利用した、メダカの高効率遺伝子導入用ベクターです。
      両末端配列を 100 bp ずつに短縮しても高い転移活性が保たれ、生殖系列への導入率は 62.7% と、魚類では非常に高い値です。
      転移酵素 mRNA 合成用の <strong>pCS2-Tip100</strong>、体細胞への導入効率の評価に適した <strong>pBS-Tip100-LR100-actb4k-EGFP</strong>（メダカ actb 4 kb プロモーター）、
      生殖系列への導入の判定と系統樹立に適した <strong>pBS-Tip100-LR100-olvas-EGFP</strong>（olvas プロモーター）の 3 種類があり、
      NBRP アサガオから分譲されています（MTA の締結と手数料が必要です）。<br>原著論文: <a href="https://doi.org/10.1007/s11248-025-00466-5"><em>Tanaka et al., 2025</em></a></p></li>
  </ul>
</section>
""",
    "en": """
<section>
  <h2>Protocols</h2>
  <ul class="res">
    <li><a href="{p}files/CRISPR_en.pdf">CRISPR/Cas9 Protocol</a> <span class="meta">English · PDF 1.5MB · <a href="https://doi.org/10.1242/bio.20148177">Ansai &amp; Kinoshita, 2014</a>; <a href="https://doi.org/10.1111/dgd.12104">Ansai et al., 2014</a> (HMA)</span>
      <p>Includes detailed methods for mutation detection.</p></li>
    <li><a href="{p}files/CRISPRv3_jp.pdf">CRISPR/Cas9 Protocol v3.0</a> <span class="meta">Japanese · PDF 247KB</span>
      <p>Fully plasmid-free sgRNA synthesis.</p></li>
    <li><a href="{p}files/CRISPR_jp.pdf">CRISPR/Cas9 Protocol v1.4.1</a> <span class="meta">Japanese · PDF 166KB</span></li>
    <li><a href="{p}files/TALEN_protocol.pdf">TALEN Protocol v1.0</a> <span class="meta">Japanese · PDF 1.8MB · <a href="https://doi.org/10.1534/genetics.112.147645">Ansai et al., 2013</a></span></li>
  </ul>
</section>
<section>
  <h2>sgRNA design tools</h2>
  <ul class="res">
    <li><a href="{p}files/sgRNA_PCRoligo.xlsx">sgRNA_PCRoligo.xlsx</a> <span class="meta">Excel · 10KB</span>
      <p>Oligo design sheet for PCR-based sgRNA templates.</p></li>
    <li><a href="{p}files/sgRNA_design.xls">sgRNA_design.xls</a> <span class="meta">Excel · 35KB</span> /
        <a href="{p}files/sgRNA_design.ods">sgRNA_design.ods</a> <span class="meta">OpenOffice · 22KB</span>
      <p>Oligo design tool for cloning into pDR274 (uses macros).</p></li>
  </ul>
</section>
<section>
  <h2>Vectors</h2>
  <ul class="res">
    <li><strong>pCS2+hSpCas9</strong> <span class="meta"><a href="{p}files/pCS2+hSpCas9.pdf">Map (PDF)</a> · <a href="{p}files/pCS2+hSpCas9.gb">Sequence (GenBank)</a> · <a href="https://www.addgene.org/51815/">Addgene #51815</a></span>
      <p>Human codon-optimized SpCas9 in pCS2+ for Cas9 mRNA synthesis (SP6). Works efficiently in fertilized eggs of
      aquatic animals, mainly teleosts such as medaka, zebrafish and various aquaculture species, and has also been used in cyclostome and amphibian embryos.<br>Original paper: <a href="https://doi.org/10.1242/bio.20148177"><em>Ansai &amp; Kinoshita, 2014</em></a></p></li>
    <li><strong>pUC-BaitD-Xhbb-EGFP</strong> <span class="meta"><a href="https://github.com/satoshi-ansai/Plasmids/blob/main/NHEJ_KI/pUC-BaitD-Xhbb-EGFP.gb">Sequence (GenBank)</a> · <a href="https://github.com/satoshi-ansai/Plasmids">GitHub: Plasmids</a></span>
      <p>Donor vector for NHEJ-based Cas9 knock-in. It carries a minimal promoter from the
      <em>Xenopus</em> beta-globin gene, which keeps background expression low.<br>Original paper: <a href="https://doi.org/10.1002/dvg.23519"><em>Kayo et al., 2023</em></a></p></li>
    <li><strong>Tip100 transposon vectors</strong> <span class="meta"><a href="https://www.nibb.ac.jp/hoshino/Tip100_vector_for_Medaka.html">Sequences and distribution (Hoshino lab, NIBB)</a></span>
      <p>Vectors for highly efficient medaka transgenesis with Tip100, a DNA transposon from the common morning glory.
      The terminal sequences can be shortened to 100 bp on each end without losing transposition activity, and the
      germline transmission rate reaches 62.7%, which is exceptionally high among teleosts. Three plasmids are available:
      <strong>pCS2-Tip100</strong> for transposase mRNA synthesis, <strong>pBS-Tip100-LR100-actb4k-EGFP</strong>
      (medaka actb 4-kb promoter) for assessing somatic integration, and <strong>pBS-Tip100-LR100-olvas-EGFP</strong>
      (olvas promoter) for germline integration and stable line establishment. They are distributed by NBRP Morning Glory
      under an MTA with a distribution fee.<br>Original paper: <a href="https://doi.org/10.1007/s11248-025-00466-5"><em>Tanaka et al., 2025</em></a></p></li>
  </ul>
</section>
""",
}


# --------------------------------------------------------------------------
# researchmap data
# --------------------------------------------------------------------------
def fetch(offline):
    CACHE.mkdir(parents=True, exist_ok=True)
    data = {}
    for s in SECTIONS:
        path = CACHE / f"{s}.json"
        if not offline:
            url = f"{API}/{s}?limit=1000" if s != "profile" else API
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (site-builder)"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    path.write_bytes(r.read())
            except Exception as e:  # keep going with the cached copy
                print(f"warning: could not fetch {s}: {e}; using cache", file=sys.stderr)
        data[s] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "site-builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _year(cr):
    """Citation year: print date, else the issue's date (volume year), else first publication."""
    issue = cr.get("journal-issue") or {}
    for v in (cr.get("published-print"), issue.get("published-print"), issue.get("published-online"),
              cr.get("issued"), cr.get("published-online")):
        if v and v.get("date-parts") and v["date-parts"][0] and v["date-parts"][0][0]:
            return str(v["date-parts"][0][0])
    return ""


def doi_metadata(dois, offline):
    """Crossref volume/pages/year and PubMed review flag for each DOI (cached)."""
    cache = json.loads(DOI_META.read_text(encoding="utf-8")) if DOI_META.exists() else {}
    missing = [d for d in dois if d.lower() not in cache]
    if missing and not offline:
        for d in missing:
            try:
                cr = _get_json("https://api.crossref.org/works/" + urllib.parse.quote(d))["message"]
                cache[d.lower()] = {"volume": cr.get("volume") or "", "page": cr.get("page") or "",
                                    "article_number": cr.get("article-number") or "",
                                    "year": _year(cr), "pubtype": None}
            except Exception as e:
                print(f"warning: Crossref lookup failed for {d}: {e}", file=sys.stderr)
        need = [d for d in missing if d.lower() in cache]
        if need:
            try:
                term = " OR ".join(f'"{d}"[doi]' for d in need)
                q = urllib.parse.urlencode({"db": "pubmed", "term": term, "retmax": 500, "retmode": "json"})
                ids = _get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + q)[
                    "esearchresult"]["idlist"]
                if ids:
                    res = _get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
                                    "db=pubmed&retmode=json&id=" + ",".join(ids))["result"]
                    for i in ids:
                        r = res[i]
                        doi = next((a["value"] for a in r["articleids"] if a["idtype"] == "doi"), "").lower()
                        if doi in cache:
                            cache[doi]["pubtype"] = r.get("pubtype")
            except Exception as e:
                print(f"warning: PubMed lookup failed: {e}", file=sys.stderr)
        DOI_META.parent.mkdir(parents=True, exist_ok=True)
        DOI_META.write_text(json.dumps(cache, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return cache


def is_review(it, meta):
    doi = doi_of(it).lower()
    if doi in REVIEW_OVERRIDE:
        return REVIEW_OVERRIDE[doi]
    return any("Review" in p for p in (meta.get(doi, {}).get("pubtype") or []))


def items(data, s):
    return data[s].get("items", [])


def t(v, lang):
    """Pick the text for a language from a researchmap {ja:.., en:..} field."""
    if not v:
        return ""
    if isinstance(v, dict):
        return v.get(lang) or v.get("en" if lang == "ja" else "ja") or ""
    return str(v)


def esc(s):
    return html.escape(s or "", quote=False)


def safe_title(s):
    """Escape a title but keep <i>…</i> for species and gene names."""
    s = esc(s)
    return re.sub(r"&lt;(/?)i&gt;", r"<\1i>", s)


def fmt_ym(d, lang):
    if not d or d.startswith("9999"):
        return ""
    y, _, m = d.partition("-")
    m = m[:2]
    if lang == "ja":
        return f"{y}年{int(m)}月" if m else f"{y}年"
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{months[int(m) - 1]} {y}" if m else y


def period(a, b, lang, present):
    s, e = fmt_ym(a, lang), fmt_ym(b, lang)
    if not e and (b or "").startswith("9999"):
        e = present
    return f"{s} – {e}" if e else s


_ROLES = None


def _norm(n):
    return re.sub(r"[^a-z]", "", n.lower())


def roles_for(it):
    global _ROLES
    if _ROLES is None:
        _ROLES = json.loads(AUTHOR_ROLES.read_text(encoding="utf-8")) if AUTHOR_ROLES.exists() else {}
    r = _ROLES.get(doi_of(it).lower(), {})
    return {_norm(n) for n in r.get("corresponding", [])}, {_norm(n) for n in r.get("equal", [])}


def authors_html(it, lang):
    corr, equal = roles_for(it)
    a = it.get("authors") or {}
    names = [x.get("name", "") for x in (a.get("en") or a.get("ja") or [])]
    out = []
    for n in names:
        # "Towako HIRAKI-KAJIYAMA" -> "Towako Hiraki-Kajiyama"
        n = re.sub(r"\b[A-Z]{2,}(?:-[A-Z]{2,})*\b", lambda m: m.group(0).title(), n)
        mark = ("†" if _norm(n) in equal else "") + ("*" if _norm(n) in corr else "")
        n = esc(n)
        if re.search(r"Ansai|安齋", n, re.I):
            n = f"<strong>{n}</strong>"
        out.append(n + (f"<sup>{mark}</sup>" if mark else ""))
    return ", ".join(out)


def paper_title(it):
    return re.sub(r"\.\s*$", "", t(it.get("paper_title"), "en").strip())


def is_excluded(it):
    title = paper_title(it)
    if it.get("rm:id") in EXCLUDE_PAPER_IDS:
        return True
    if not it.get("published_paper_type"):  # preprints (bioRxiv, Research Square, ...)
        return True
    return any(re.search(p, title) for p in EXCLUDE_TITLE_PATTERNS)


def doi_of(it):
    d = (it.get("identifiers") or {}).get("doi") or []
    return d[0] if d else ""


def split_papers(data, offline=False):
    journal, chapters = [], []
    for it in items(data, "published_papers"):
        if is_excluded(it):
            continue
        title = paper_title(it)
        pub = t(it.get("publication_name"), "en")
        if it.get("published_paper_type") == "in_book" or (
                "Methods in Molecular Biology" in pub and title.lower().startswith("genome editing of medaka")):
            chapters.append(("paper", it))
        else:
            journal.append(it)
    meta = doi_metadata([doi_of(it) for it in journal if doi_of(it)], offline)
    for it in journal:
        m = meta.get(doi_of(it).lower(), {})
        it["_meta"] = m
        it["_year"] = m.get("year") or (it.get("publication_date") or "")[:4]
        it["_review"] = is_review(it, meta)
    journal.sort(key=lambda x: (x["_year"], x.get("publication_date") or ""), reverse=True)
    for it in items(data, "books_etc"):
        chapters.append(("book", it))
    chapters.sort(key=lambda c: c[1].get("publication_date") or "", reverse=True)
    return journal, chapters


def venue_html(it):
    """Journal, volume: pages (year). Issue numbers are omitted."""
    pub = t(it.get("publication_name"), "en")
    pub = JOURNAL_FIX.get(pub, pub)
    m = it.get("_meta") or {}
    vol = m.get("volume") or it.get("volume") or ""
    pages = m.get("page") or m.get("article_number") or ""
    if not pages:
        sp, ep = it.get("starting_page"), it.get("ending_page")
        pages = (sp or "") + (f"-{ep}" if sp and ep and ep != sp else "")
    pages = pages.replace("-", "–")
    year = it.get("_year") or (it.get("publication_date") or "")[:4]
    s = f"<em>{esc(pub)}</em>"
    if vol:
        s += f", {esc(vol)}"
        if pages:
            s += f": {esc(pages)}"
    s += f" ({year})" if year else ""
    if not vol:
        s += ", in press"
    return s


def paper_li(it, n=None):
    doi = doi_of(it)
    title = safe_title(paper_title(it))
    if doi:
        title = f'<a href="https://doi.org/{esc(doi)}">{title}</a>'
    num = f' value="{n}"' if n else ""
    return (f"<li{num}><span class=\"ttl\">{title}</span>"
            f"<span class=\"au\">{authors_html(it, 'en')}</span>"
            f"<span class=\"vn\">{venue_html(it)}</span></li>")


def chapter_li(kind, it, lang):
    year = (it.get("publication_date") or "")[:4]
    if kind == "paper":
        doi = doi_of(it)
        title = safe_title(paper_title(it))
        if doi:
            title = f'<a href="https://doi.org/{esc(doi)}">{title}</a>'
        bname = t(it.get("publication_name"), "en")
        bname = JOURNAL_FIX.get(bname, bname)
        book = f"<em>{esc(bname)}</em>, Springer ({year})"
        return (f"<li><span class=\"ttl\">{title}</span><span class=\"au\">{authors_html(it, lang)}</span>"
                f"<span class=\"vn\">{book}</span></li>")
    chap = esc(t(it.get("book_owner_range"), lang))
    btitle = esc(t(it.get("book_title"), lang))
    pubr = esc(t(it.get("publisher"), lang))
    a = it.get("authors") or {}
    names = [x.get("name", "") for x in (a.get(lang) or a.get("ja") or a.get("en") or [])]
    au = ", ".join(f"<strong>{esc(n)}</strong>" if re.search(r"Ansai|安齋", n) else esc(n) for n in names)
    return (f"<li><span class=\"ttl\">{chap}</span><span class=\"au\">{au}</span>"
            f"<span class=\"vn\"><em>{btitle}</em>, {pubr} ({year})</span></li>")


def grants(data):
    """Merge records that are the same project under renumbered grant IDs."""
    merged = {}
    for it in items(data, "research_projects"):
        key = t(it.get("research_project_title"), "ja")
        nums = (it.get("identifiers") or {}).get("grant_number") or []
        if key in merged:
            m = merged[key]
            m["from_date"] = min(m["from_date"], it.get("from_date") or m["from_date"])
            m["to_date"] = max(m["to_date"], it.get("to_date") or m["to_date"])
            m["nums"] += [n for n in nums if n not in m["nums"]]
        else:
            merged[key] = dict(it, nums=list(nums), from_date=it.get("from_date") or "",
                               to_date=it.get("to_date") or "")
    return sorted(merged.values(), key=lambda g: (g["from_date"], g["to_date"]), reverse=True)


def grant_role(g):
    inv = (g.get("investigators") or {})
    names = [x.get("name", "") for x in (inv.get("ja") or inv.get("en") or [])]
    return "pi" if names and re.search(r"安齋|Ansai", names[0]) else "co"


# --------------------------------------------------------------------------
# Page rendering
# --------------------------------------------------------------------------
def layout(lang, page, title, body, desc=""):
    c = CONTENT[lang]
    p = "" if lang == "ja" else "../"            # path to site root
    other = ("en/" if lang == "ja" else "../") + f"{page}.html"
    other_label = "EN" if lang == "ja" else "日本語"
    cur = ' aria-current="page"'
    nav = "".join(
        f'<a href="{k}.html"{cur if k == page else ""}>{v}</a>'
        for k, v in c["nav"].items())
    full_title = "Satoshi Ansai" if page == "index" else f"{title} | Satoshi Ansai"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{esc(desc or c['intro'])}">
<link rel="alternate" hreflang="{'en' if lang == 'ja' else 'ja'}" href="{other}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{p}assets/style.css">
</head>
<body>
<header class="site">
  <div class="wrap bar">
    <a class="brand" href="index.html">Satoshi Ansai</a>
    <nav>{nav}<a class="lang" href="{other}" hreflang="{'en' if lang == 'ja' else 'ja'}">{other_label}</a></nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="wrap site">
  <p>© 2026– Satoshi Ansai</p>
</footer>
{MAIL_JS}
</body>
</html>
"""


def profile_contact_html(lang):
    """Postal-style contact block for the Profile page."""
    c = CONTENT[lang]
    name = c["name"] if lang == "ja" else "Satoshi Ansai"
    if lang == "ja":
        lines = [esc(c["address"]), esc(c["affiliation"][0]), esc(name)]
    else:  # English convention: name, institution, address
        lines = [esc(name), esc(c["affiliation"][0]), esc(c["address"])]
    lines += [f"Tel: {esc(c['tel'])}", f"E-mail: {mail_html(c['email'])}"]
    return "<address>" + "<br>".join(lines) + "</address>"


def links_html():
    return '<ul class="links">' + "".join(
        f'<li><a href="{u}">{esc(n)}</a></li>' for n, u in LINKS) + "</ul>"


def mail_html(addr):
    """Spam protection: the address is stored reversed and base64-encoded and is
    turned into a mailto link by a small script; crawlers see only obfuscated text."""
    enc = base64.b64encode(addr[::-1].encode()).decode()
    user, _, domain = addr.partition("@")
    fallback = f"{user} [at] {domain.replace('.', ' [dot] ')}"
    return f'<span class="mail" data-m="{enc}">{esc(fallback)}</span>'


MAIL_JS = """<script>
document.querySelectorAll('.mail[data-m]').forEach(function (el) {
  var a = document.createElement('a');
  var m = atob(el.dataset.m).split('').reverse().join('');
  a.href = 'mailto:' + m; a.textContent = m; el.replaceWith(a);
});
</script>"""


def contact_html(lang, address=True):
    c = CONTENT[lang]
    lines = [esc(c["title"])] + [esc(a) for a in c["affiliation"]]
    if address:
        lines.append(esc(c["address"]))
    if c.get("tel"):
        lines.append(f"Tel: {esc(c['tel'])}")
    if c["email"]:
        lines.append(f"E-mail: {mail_html(c['email'])}")
    return "<address>" + "<br>".join(lines) + "</address>"


def page_index(data, lang, journal):
    c, h = CONTENT[lang], CONTENT[lang]["h"]
    kw = [t(it.get("keyword"), lang) for it in items(data, "research_interests")]
    body = f"""
<section class="hero">
  <h1>{esc(c['name'])}<span class="sub">{esc(c['name_sub'])}</span></h1>
  {contact_html(lang)}
  {links_html()}
</section>
<section>
  <p class="lead">{esc(c['intro'])}</p>
  <h2>{h['interests']}</h2>
  <ul class="tags">{''.join(f'<li>{esc(k)}</li>' for k in kw)}</ul>
</section>
"""
    return layout(lang, "index", "Top", body)


def cv_rows(rows):
    return '<dl class="cv">' + "".join(f"<dt>{d}</dt><dd>{v}</dd>" for d, v in rows) + "</dl>"


def page_profile(data, lang):
    c, h = CONTENT[lang], CONTENT[lang]["h"]
    career = []
    for it in sorted(items(data, "research_experience"), key=lambda x: x.get("from_date", ""), reverse=True):
        parts = [t(it.get("affiliation"), lang), t(it.get("section"), lang), t(it.get("job"), lang)]
        career.append((period(it.get("from_date"), it.get("to_date"), lang, h["present"]),
                       esc(" ".join(p for p in parts if p) if lang == "ja" else ", ".join(
                           p for p in [t(it.get("job"), lang), t(it.get("section"), lang),
                                       t(it.get("affiliation"), lang)] if p))))
    edu = []
    for it in sorted(items(data, "education"), key=lambda x: x.get("from_date", ""), reverse=True):
        parts = [t(it.get("affiliation"), lang), t(it.get("department"), lang), t(it.get("course"), lang)]
        note = t(it.get("note"), "ja") if lang == "ja" else ""
        txt = " ".join(p for p in parts + [note] if p) if lang == "ja" else ", ".join(
            p for p in reversed(parts) if p)
        edu.append((period(it.get("from_date"), it.get("to_date"), lang, h["present"]), esc(txt)))
    deg = data["profile"].get("degrees") or []
    deg_rows = [(fmt_ym(d.get("degree_date"), lang),
                 esc(("博士（農学）京都大学" if lang == "ja" else "Ph.D. in Agriculture, Kyoto University")))
                for d in deg]
    # grants grouped as {kakenhi|other} x {pi|co}
    g_groups = {(k, r): [] for k in ("kaken", "other") for r in ("pi", "co")}
    for g in grants(data):
        title = t(g.get("research_project_title"), lang)
        cat = t(g.get("category"), lang)
        sysn = t(g.get("system_name"), lang)
        org = t(g.get("offer_organization"), lang)
        is_kaken = "科学研究費" in t(g.get("system_name"), "ja")
        src = cat if is_kaken else " ".join(x for x in [org, sysn, cat] if x)
        nums = f" ({', '.join(g['nums'])})" if g["nums"] else ""
        g_groups[("kaken" if is_kaken else "other", grant_role(g))].append(
            (period(g["from_date"][:7], g["to_date"][:7], lang, h["present"]),
             f"<span class=\"gt\">{esc(title)}</span><span class=\"meta\">{esc(src)}{esc(nums)}</span>"))
    g_html = ""
    for k in ("kaken", "other"):
        g_html += f"<h3 class=\"gk\">{h[k]}</h3>"
        for r in ("pi", "co"):
            if g_groups[(k, r)]:
                g_html += f"<h4>{h[r]}</h4>{cv_rows(g_groups[(k, r)])}"
    aw = [(fmt_ym(it.get("award_date"), lang),
           f"{esc(t(it.get('award_name'), lang))}, {esc(t(it.get('association'), lang))}")
          for it in sorted(items(data, "awards"), key=lambda x: x.get("award_date", ""), reverse=True)]
    soc = [esc(t(it.get("academic_society_name"), lang)) for it in items(data, "association_memberships")]
    body = f"""
<h1 class="page">Profile</h1>
<section><h2>{h['contact']}</h2>{profile_contact_html(lang)}{links_html()}</section>
<section><h2>{h['career']}</h2>{cv_rows(career)}</section>
<section><h2>{h['education']}</h2>{cv_rows(edu)}</section>
<section><h2>{h['degree']}</h2>{cv_rows(deg_rows)}</section>
<section><h2>{h['grants']}</h2>{g_html}</section>
<section><h2>{h['awards']}</h2>{cv_rows(aw)}</section>
<section><h2>{h['societies']}</h2><ul class="tags">{''.join(f'<li>{s}</li>' for s in soc)}</ul></section>
<section><h2>{h['courses']}</h2><ul class="simple">{''.join(f'<li>{esc(x)}</li>' for x in COURSES[lang])}</ul></section>
"""
    return layout(lang, "profile", "Profile", body)


def page_research(lang):
    c = CONTENT[lang]
    label = "Key publications"
    blocks = []
    for i, (h, p) in enumerate(c["research"], 1):
        refs = RESEARCH_REFS[i - 1] if i - 1 < len(RESEARCH_REFS) else []
        cites = "".join(
            f'<li><a href="https://doi.org/{d}">{t}</a></li>' for t, d in refs)
        cites = f'<div class="refs"><span>{label}</span><ul>{cites}</ul></div>' if cites else ""
        blocks.append(
            f'<section class="topic"><h2><span class="n">{i:02d}</span>{esc(h)}</h2>'
            f'<p>{esc(p)}</p>{cites}</section>')
    blocks = "".join(blocks)
    lead = (f'<h1 class="page">{esc(c["research_title"])}</h1>'
            f'<p class="lead">{esc(c["research_lead"])}</p>')
    return layout(lang, "research", "Research", f'{lead}\n{blocks}')


def pub_list(papers, anchor):
    """Numbered list grouped by year headings; returns (html, years)."""
    n, out, years, cur = len(papers), [], [], None
    for i, it in enumerate(papers):
        y = it["_year"]
        if y != cur:
            if cur is not None:
                out.append("</ol>")
            out.append(f'<h3 id="{anchor}{y}">{y}</h3><ol class="pubs" reversed>')
            years.append(y)
            cur = y
        out.append(paper_li(it, n - i))
    if papers:
        out.append("</ol>")
    return "".join(out), years


def page_publications(lang, journal, chapters):
    h = CONTENT[lang]["h"]
    originals = [it for it in journal if not it["_review"]]
    reviews = [it for it in journal if it["_review"]]
    orig_html, years = pub_list(originals, "y")
    rev_items = "".join(paper_li(it, len(reviews) - i) for i, it in enumerate(reviews))
    jump = " ".join(f'<a href="#y{y}">{y}</a>' for y in years)
    ch = "".join(chapter_li(k, it, lang) for k, it in chapters)
    body = f"""
<h1 class="page">Publications</h1>
{links_html()}
<p class="note">{h['marks']}</p>
<p class="jump"><a href="#original">{h['papers']}</a> · <a href="#reviews">{h['reviews']}</a> · <a href="#chapters">{h['chapters']}</a></p>
<section id="original">
  <h2>{h['papers']} <span class="count">{len(originals)}</span></h2>
  <p class="jump">{jump}</p>
  {orig_html}
</section>
<section id="reviews">
  <h2>{h['reviews']} <span class="count">{len(reviews)}</span></h2>
  <ol class="pubs" reversed>{rev_items}</ol>
</section>
<section id="chapters">
  <h2>{h['chapters']} <span class="count">{len(chapters)}</span></h2>
  <ol class="pubs plain">{ch}</ol>
</section>
"""
    return layout(lang, "publications", "Publications", body)


def page_resources(lang):
    p = "" if lang == "ja" else "../"
    return layout(lang, "resources", "Resources",
                  '<h1 class="page">Resources</h1>\n' + RESOURCES[lang].replace("{p}", p))


def main():
    offline = "--offline" in sys.argv
    data = fetch(offline)
    journal, chapters = split_papers(data, offline)
    for lang in ("ja", "en"):
        out = ROOT if lang == "ja" else ROOT / "en"
        out.mkdir(exist_ok=True)
        pages = {
            "index": page_index(data, lang, journal),
            "profile": page_profile(data, lang),
            "research": page_research(lang),
            "publications": page_publications(lang, journal, chapters),
            "resources": page_resources(lang),
        }
        for name, content in pages.items():
            (out / f"{name}.html").write_text(content, encoding="utf-8")
    n_rev = sum(it["_review"] for it in journal)
    print(f"built: {len(journal) - n_rev} original articles, {n_rev} reviews, {len(chapters)} chapters")


if __name__ == "__main__":
    main()
