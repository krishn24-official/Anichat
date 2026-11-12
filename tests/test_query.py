

def test_other_words_for_chapters_and_episodes():
    from anichat.domain.query import parse_question

    assert parse_question("What happens in Reincarnation 1?").chapter == 1
    assert parse_question("Summarise Act 12 of Rurouni Kenshin").chapter == 12
    assert parse_question("What is lesson 5 about?").chapter == 5
    assert parse_question("Which session introduces Ed? session 9").episode == 9
    assert parse_question("Why did he act like that in the fight?").chapter is None
