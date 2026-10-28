import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ragnarok import textproc as tp


class T(unittest.TestCase):
    def test_chapters_by_heading(self):
        b = tp.parse_markdown("# Um\n\nTexto um.\n\n# Dois\n\nTexto dois.\n\n## Sub\n\nMais.\n")
        self.assertEqual([c.title for c in b.chapters], ["Um", "Dois"])
        self.assertEqual([(p.kind, p.text) for p in b.chapters[1].paras], [("p", "Texto dois."), ("sub", "Sub"), ("p", "Mais.")])

    def test_no_heading_is_one_implicit_chapter(self):
        b = tp.parse_markdown("Só um parágrafo.\n\nOutro.", default_title="arq")
        self.assertEqual(len(b.chapters), 1)
        self.assertTrue(b.chapters[0].implicit)
        units, _ = tp.book_to_units(b)
        self.assertFalse(any(u.kind == "title" for u in units))

    def test_intro_before_first_heading(self):
        b = tp.parse_markdown("Prefácio solto.\n\n# Cap\n\nTexto.")
        self.assertEqual([c.title for c in b.chapters], ["Início", "Cap"])
        self.assertTrue(b.chapters[0].implicit)

    def test_clean_markdown(self):
        t = tp.clean_inline("**negrito** e *itálico* e [link](http://x.y) ![img](a.png) `code` snake_case_word")
        self.assertEqual(t, "negrito e itálico e link code snake_case_word")

    def test_code_fence_skipped_and_front_matter(self):
        b = tp.parse_markdown("---\ntitle: Meu Livro\nauthor: L\n---\n# A\n\n```\nprint(1)\n```\n\nTexto.")
        self.assertEqual(b.title, "Meu Livro"); self.assertEqual(b.author, "L")
        self.assertEqual([p.text for p in b.chapters[0].paras], ["Texto."])

    def test_abbreviations_not_split(self):
        s = tp.split_sentences("O Sr. Silva chegou. Falou com a Dra. Ana! Depois saiu... E voltou?")
        self.assertEqual(s[0], "O Sr. Silva chegou.")
        self.assertEqual(s[1], "Falou com a Dra. Ana!")

    def test_chunks_bounded_and_pauses(self):
        long = " ".join(["palavra"] * 200) + "."
        cks = tp.chunk_paragraph(long)
        self.assertTrue(all(len(c) <= tp.HARD_MAX for c, _ in cks))
        self.assertGreater(len(cks), 3)
        c = tp.chunk_paragraph("Será? Sim! Talvez… Não.")
        self.assertTrue(all(p > 0 for _, p in c))
        self.assertEqual(tp.pause_for("Fim…"), tp.PAUSE_ELLIPSIS)
        self.assertEqual(tp.pause_for("Fim?"), tp.PAUSE_STRONG)
        self.assertEqual(tp.pause_for("Fim."), tp.PAUSE_PERIOD)

    def test_paragraph_end_pause(self):
        b = tp.parse_markdown("Primeira frase. Segunda frase mais comprida para não agrupar com a primeira, de jeito nenhum, certo.\n\nNovo.")
        units, _ = tp.book_to_units(b)
        self.assertGreaterEqual(units[0].pause, tp.PAUSE_PERIOD)
        self.assertGreaterEqual(units[-1].pause, tp.PAUSE_PARAGRAPH)

    def test_unspeakable_dropped(self):
        self.assertEqual(tp.chunk_paragraph("*** ---"), [])


if __name__ == "__main__":
    unittest.main()
