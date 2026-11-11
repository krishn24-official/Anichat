/** Two sample TMDb movies for the local admin preview (dev/adminPreview.ts) when no TMDb token is set. */

const MOVIES = [
  {
    id: 1726, title: 'Iron Man', original_title: 'Iron Man', release_date: '2008-04-30', runtime: 126, budget: 140000000,
    revenue: 585174222, original_language: 'en', spoken_languages: [{ iso_639_1: 'en', english_name: 'English' }],
    genres: [{ name: 'Action' }, { name: 'Science Fiction' }, { name: 'Adventure' }], tagline: "Heroes aren't born. They're built.",
    overview: 'After being held captive in an Afghan cave, billionaire engineer Tony Stark creates a unique weaponized suit of armor to fight evil.',
    credits: {
      cast: [['Robert Downey Jr.', 'Tony Stark'], ['Terrence Howard', 'Rhodey'], ['Jeff Bridges', 'Obadiah Stane'],
        ['Gwyneth Paltrow', 'Pepper Potts'], ['Leslie Bibb', 'Christine Everhart'], ['Shaun Toub', 'Yinsen'],
        ['Faran Tahir', 'Raza'], ['Clark Gregg', 'Agent Coulson'], ['Jon Favreau', 'Hogan']].map(([name, character]) => ({ name, character })),
      crew: [{ name: 'Jon Favreau', job: 'Director' }, { name: 'Mark Fergus', job: 'Screenplay' },
        { name: 'Kevin Feige', job: 'Producer' }, { name: 'Ramin Djawadi', job: 'Original Music Composer' }],
    },
  },
  {
    id: 1112426, title: 'Stree 2', original_title: 'स्त्री 2', release_date: '2024-08-15', runtime: 147, budget: 0, revenue: 0,
    original_language: 'hi', spoken_languages: [{ iso_639_1: 'hi', english_name: 'Hindi' }],
    genres: [{ name: 'Comedy' }, { name: 'Horror' }], tagline: 'Sarkate ka aatank',
    overview: 'The town of Chanderi is being haunted again. This time, women are mysteriously abducted by a terrifying headless entity.',
    credits: {
      cast: [['Rajkummar Rao', 'Vicky'], ['Shraddha Kapoor', 'Stree'], ['Pankaj Tripathi', 'Rudra'],
        ['Abhishek Banerjee', 'Jana'], ['Aparshakti Khurana', 'Bittu'], ['Tamannaah Bhatia', 'Shama']]
        .map(([name, character]) => ({ name, character })),
      crew: [{ name: 'Amar Kaushik', job: 'Director' }, { name: 'Niren Bhatt', job: 'Screenplay' },
        { name: 'Dinesh Vijan', job: 'Producer' }, { name: 'Sachin-Jigar', job: 'Original Music Composer' }],
    },
  },
]

/** Answer a TMDb API URL (search or details) from the samples. Called by: dev/adminPreview.ts */
export async function sampleTmdb(url: string): Promise<Response> {
  const u = new URL(url)
  const details = u.pathname.match(/\/3\/movie\/(\d+)$/)
  if (details) {
    const movie = MOVIES.find((m) => m.id === Number(details[1]))
    return movie ? Response.json(movie) : new Response('{}', { status: 404 })
  }
  const q = (u.searchParams.get('query') ?? '').toLowerCase()
  const results = MOVIES.filter((m) => m.title.toLowerCase().includes(q) || q.includes(m.title.toLowerCase()))
    .map((m) => ({ id: m.id, title: m.title, release_date: m.release_date, overview: m.overview, popularity: 50 }))
  return Response.json({ results })
}
