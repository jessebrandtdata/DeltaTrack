# Classifier codebook: what each label means

How to label a paragraph in `classifier_labels.toml` so `classifier_agreement.py` can score
`classify_text` (`classify_bill.py`). The classifier's labels were defined only by the regex
that produces each one; this gives every label a definition a person can apply without
reading the regex, and a rule for each place two labels overlap.

Where a label is a term of federal budget law, the definition is GAO's, quoted from
*A Glossary of Terms Used in the Federal Budget Process* (GAO-05-734SP, 2005). Where it is
not (`cap`, `directive`, `availability`, `sub_allocation`), the definition describes the clause
the classifier is naming, and says so. Decision rules are proposals for this labelling pass;
the examples are rows from the committed sample, cited as `[jurisdiction #node_ordinal]`.

## The unit, and the one question that matters

A row is one paragraph of a bill: a node's body text, usually one unnumbered account
paragraph or one general-provision subsection. Label what the paragraph **does**, not what
clauses it contains. An account paragraph nearly always carries a "not to exceed" cap, a
period of availability and an "of which" set-aside, and is still an appropriation.

The downstream scorers (`committee_agreement.py`, `typed_precision.py`) read only paragraphs
the classifier calls `appropriation`, so the distinction that decides their numbers is
appropriation-or-not. The coarse pass labels only that: `appropriation`, or
`not_appropriation` when the paragraph is some other class and you did not decide which. The
full pass names the class. Either is a complete label for a row.

## Labels that are fiscal actions (GAO terms)

### appropriation

GAO: "Budget authority to incur obligations and to make payments from the Treasury for
specified purposes. An appropriation act is the most common means of providing
appropriations; however, authorizing and other legislation itself may provide
appropriations." And the unit: "The basic unit of an appropriation generally reflecting each
unnumbered paragraph in an appropriation act. An appropriation account typically encompasses
a number of activities or projects and may be subject to restrictions or conditions."

Label `appropriation` when the paragraph makes money available to obligate that was not
available before: "For necessary expenses of …, $X", "For an additional amount for …, $X",
"there is hereby appropriated", or an indefinite grant such as "is authorized to make such
expenditures … within the limits of funds and borrowing authority available" under an account
heading. The caps, availability clauses and set-asides inside it do not change the label.

- `[defense #53]` "For expenses of activities and agencies of the Department of Defense …
  $5,819,954,000, to remain available for obligation until September 30, 2027: Provided, That
  of the amounts made available under this heading, $527,245,000 is designated …" An
  appropriation with an availability clause and a designation inside it.
- `[agriculture #8]` "For necessary expenses of the Office of the Chief Information Officer,
  $91,400,000, of which not less than $77,428,000 is for cybersecurity requirements." An
  appropriation with a set-aside; still `appropriation`.
- `[state_foreign_ops #85]` "The United States International Development Finance Corporation
  … is authorized to make such expenditures and commitments within the limits of funds and
  borrowing authority available to the Corporation …" An indefinite account paragraph under
  the Corporate Capital Account heading. The classifier says `availability`; the proposed
  label is `appropriation`, with a note. Hard case: decide and record the reasoning.

### rescission

GAO: "Legislation enacted by Congress that cancels the availability of budget authority
previously enacted before the authority would otherwise expire."

Label `rescission` when the paragraph cancels budget authority, whatever it opens with: "Of
the unobligated balances …, $X is hereby rescinded", "are hereby rescinded", or a list of
accounts "from which the following funds are hereby rescinded". A paragraph that both
rescinds and re-appropriates the same money is a rescission (the classifier's rule too).

- `[milcon_va #155]` "Of the unobligated balances from amounts made available under the
  heading Medical and Prosthetic Research …, $5,000,000 is hereby rescinded."
- `[homeland_security #245]` "Of the funds appropriated to the Department of Homeland
  Security, the following funds are hereby rescinded from the following accounts …"

### transfer

GAO: "Shifting of all or part of the budget authority in one appropriation or fund account
to another. Agencies may transfer budget authority only as specifically authorized by law."
GAO distinguishes it from reprogramming, "shifting funds within an appropriation or fund
account", which no label here names (see `cap`).

Label `transfer` when the paragraph moves or permits moving money from one account to
another: "Of the amounts appropriated … for Medical Services …, up to $X may be transferred
to …", "shall be transferred to the … Fund".

- `[milcon_va #96]` "Of the amounts appropriated to the Department of Veterans Affairs …,
  up to $644,025,000, plus reimbursements, may be transferred to …"
- `[milcon_va #98]` "… a minimum of $15,000,000 shall be transferred to the DOD–VA Health
  Care Sharing Incentive Fund."

Overlap: a general provision that authorizes transfers "not to exceed $X" of working capital
funds is a transfer authority with a ceiling. The classifier calls it `cap`
(`[defense #74]`, section 8005); the proposed label is `transfer`, since what the paragraph
does is permit a transfer. Record the disagreement in the note.

### authorization

GAO: "Authorization of appropriations legislation authorizes the enactment of appropriations
of specific amounts for specific programs and activities to be provided in an appropriation
act." It does not itself provide budget authority.

Label `authorization` when the paragraph says money may later be appropriated ("there is
authorized to be appropriated", "Subscription authorized") and does not appropriate it. When
a paragraph says "there is authorized to be appropriated, and there is hereby appropriated",
money is provided: label `appropriation`.

- `[state_foreign_ops #421]` amends the African Development Bank Act to add "Subscription
  authorized … The United States Governor of the Bank may subscribe …": an authorization
  written as an amendment to another law.
- `[transportation_hud #69]` "(b) In this section, the term earmarked amount means …
  which was authorized to be appropriated …" is a **definition**, not an authorization. The
  classifier's `authorization` fires on the phrase; the proposed label is `unknown`.

### restriction

GAO has no headword "restriction"; the nearest are **Limitation**, "A restriction on the
amount, purpose, or period of availability of budget authority", and **Appropriation
Rider**, "a limitation or requirement in an appropriation act".

Label `restriction` when the paragraph forbids a use of funds: "None of the funds made
available by this Act may be used to …", including when a dollar amount appears in the
forbidden use. The restriction is on the money; a command to an agency that is not framed as
a use of funds is a `directive` (below).

- `[transportation_hud #292]` "None of the funds appropriated or otherwise made available by
  this Act may be used to pay award or incentive fees for contractors whose performance has
  been judged to be below satisfactory …"
- `[cjs #156]` "(a) None of the funds … may be used by the Departments of Commerce and
  Justice … to acquire a high-impact or moderate-impact information system …"

### fee

GAO, **User Fee/User Charge**: "A fee assessed to users for goods or services provided by the
federal government."

Label `fee` when the paragraph sets or authorizes a fixed-dollar fee ("a fee of $X", "impose
a fee"). Fee-schedule machinery whose amount is set by future rulemaking is `unknown`
(`classifier_notes.md`, "What stays unknown", item 3). No paragraph in the Senate-reported
sample was predicted `fee`; it appears in reconciliation bills.

## Labels that name a clause (not GAO categories)

These four describe a drafting feature that normally lives *inside* an appropriation
paragraph. A paragraph gets one of them as its label only when the clause is all the
paragraph does, which happens in general provisions that reach back into an account. Inside
an account paragraph the clause is part of the appropriation and the label is
`appropriation`.

### cap

The classifier's bucket for two different things: a "not to exceed $X" or "not more than $X"
ceiling on a use of funds, and a reprogramming limit ("no project may be increased or
decreased"). GAO calls the first a limitation on amount and the second reprogramming
oversight; neither is a category of paragraph.

Label `cap` when the paragraph's whole work is to put a ceiling on an amount that other
language has already made available, and the ceiling is not a transfer authority (see
`transfer`) or a restriction on purpose (see `restriction`).

- `[defense #112]` "(d) … of the funds available to the department during fiscal year 2025,
  not more than $2,886,300,000 may be funded for professional technical staff-related costs
  of the defense FFRDCs …" A ceiling on an existing appropriation.
- `[financial_services #15]` "To carry out the Riegle Community Development and Regulatory
  Improvement Act of 1994 …, but at rates for individuals not to exceed the per diem rate …,
  $X …" opens an **account paragraph**; the "not to exceed" is the per-diem cap boilerplate
  and the paragraph appropriates. The classifier says `cap`; the proposed label is
  `appropriation`.

### availability

GAO on duration: "**No-Year Authority.** Budget authority that remains available for
obligation for an indefinite period of time. A no-year appropriation is usually identified by
language such as 'to remain available until expended.'" One-year and multiple-year authority
are the other durations.

Label `availability` when the paragraph's whole work is to set or extend the period in which
already-appropriated money may be obligated: "Of the amounts appropriated in this Act under
the heading …, $X shall remain available until expended."

- `[defense #172]` "Of the amounts appropriated in this Act under the heading Operation and
  Maintenance, Army, $194,452,598 shall remain available until expended: Provided, That …
  the Secretary of Defense is authorized to transfer such funds …" Primarily an availability
  provision; the transfer proviso is secondary. Note it.

### sub_allocation

A set-aside within a lump sum: "of which $X shall be for …", ", $X shall be available for
…". GAO's **Earmarking** (2) covers this: "Designating any portion of a lump-sum amount for
particular purposes by means of legislative language." The classifier reserves `earmark` for
the table-directed form (next), so a plain set-aside is `sub_allocation`.

Label `sub_allocation` when the paragraph's whole work is to designate part of an existing
amount for a purpose, and the designation is not by reference to a table.

### earmark

The classifier's name for one specific set-aside: an amount "under this heading … specified
in the table" of the bill or report, that is, congressionally directed spending. GAO's
**Earmarking** (2) applies, and GAO notes the word "is colloquially used to characterize
directions included in congressional committee reports but not in the legislation itself."

Label `earmark` when the paragraph's whole work is to direct amounts under a heading to the
projects a table lists.

### directive

Not a budget-law term. A command or prohibition addressed to an agency or official ("The
Secretary shall …", "may not …") that is not framed as a use of funds.

Label `directive` when the paragraph tells someone to do or not do something and does not
make, cancel, move, cap or forbid the use of money. If it forbids a use of funds, it is a
`restriction`; if it sets aside money, it is a `sub_allocation`.

- `[interior_environment #71]` "The United States Fish and Wildlife Service shall …
  implement a system of mass marking of salmonid stocks …"
- `[agriculture #158]` "The Secretary shall set aside for Rural Economic Area Partnership
  (REAP) Zones … an amount of funds made available in title III under the headings …" A
  command whose content is a set-aside. The classifier says `directive`; `sub_allocation`
  is defensible. Decide and note it.

## unknown

None of the eleven fits. `classifier_notes.md` lists what the classifier leaves `unknown` on
purpose: amendments to other laws, tax-code text, definitions, tables, loan-portfolio
ceilings, placeholder nodes. Two further cases from the sample:

- `[financial_services #199]` "(b) For purposes of this section, the term Executive agency
  covered by this Act means …" A definition. The classifier's `appropriation` fires on the
  opening "For"; this is the false positive `classifier_notes.md` describes. Label `unknown`.
- `[defense #95]` "No more than $500,000 of the funds appropriated or made available in this
  Act shall be used during a single fiscal year for any single relocation …" The classifier
  says `unknown` (no pattern matches "No more than" at the start). It is a ceiling on a use
  of funds: `cap` by the definition above. Label what it is, not what the classifier missed.

## Decision rules, in order

1. Makes new money available to obligate: `appropriation`, whatever else the paragraph
   contains.
2. Cancels budget authority: `rescission`, even if it opens with "For" or "Of the amounts".
3. Moves money between accounts, or permits it: `transfer`, even with a ceiling.
4. Forbids a use of funds: `restriction`, even with a dollar amount in the forbidden use.
5. Authorizes a future appropriation without making one: `authorization`.
6. Only sets a ceiling, a period, a set-aside or a table-directed amount on money already
   made available: `cap`, `availability`, `sub_allocation`, `earmark`.
7. Commands an agency and does none of the above: `directive`.
8. A definition, an amendment to another law, a table, a placeholder: `unknown`.
9. When two rules apply and the order above does not settle it, pick one, and write the
   competing label in `note`. The note is the data the next revision of these rules is
   written from.

In the coarse pass, rule 1 is the whole decision: `appropriation` if it applies, otherwise
`not_appropriation`.
