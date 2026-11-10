/** Example questions shown on the empty chat screen, per franchise. */

const EXAMPLES: Record<string, string[]> = {
  demon_slayer: ['Who is Upper Rank Three?', 'How did Rengoku die?', 'What is Sun Breathing?'],
  death_note: ['Who killed L?', 'What are the rules of the Death Note?', 'Who is Ryuk?'],
  attack_on_titan: ['Who killed Eren Yeager?', 'What is the Founding Titan?', 'What is the Rumbling?'],
  jujutsu_kaisen: ['What is Malevolent Shrine?', 'How was Gojo sealed?', 'Who is Kenjaku?'],
  naruto: ["Who is Naruto's father?", 'Who is the Third Hokage?', 'What is the Rasengan?'],
  one_piece: ['Who killed Portgas D. Ace?', 'What is the Gomu Gomu no Mi?', 'What is the Void Century?'],
  vinland_saga: ['Who killed Askeladd?', 'Who is Thorkell?', 'What is Vinland?'],
  solo_leveling: ['Who is Beru?', 'What is Shadow Extraction?', 'Who is Antares?'],
  hunter_x_hunter: ['What is Nen?', 'Who is Meruem?', "Who is Gon's father?"],
  black_clover: ['What is Anti Magic?', 'Who is the captain of the Black Bulls?', 'Who is Liebe?'],
  dragon_ball: ['What are the Dragon Balls?', 'What is Ultra Instinct?', "Who is Goku's father?"],
  chainsaw_man: ['Who is Makima?', 'Who is Pochita?', 'What is a Fiend?'],
  spy_x_family: ['What is Operation Strix?', 'Who is Yor Forger?', 'What can Anya do?'],
  fullmetal_alchemist: ["What is a Philosopher's Stone?", 'Who is Scar?', 'What is the Gate?'],
}

const MIXED = ['Who killed Eren Yeager?', 'What is Nen?', 'Who is Tobi?', 'What happens in One Piece chapter 1044?']

/**
 * Up to four example questions for the selected franchise, or a mix across series.
 * Called by: components/EmptyState.tsx
 */
export function examplesFor(franchise: string | null): string[] {
  return (franchise && EXAMPLES[franchise]) || MIXED
}
