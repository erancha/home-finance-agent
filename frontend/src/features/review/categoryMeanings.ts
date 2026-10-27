/** What each budget category covers, word for word as the A2A contract's taxonomy table says it;
 * a test holds the two together. */
export const CATEGORY_MEANINGS: Record<string, string> = {
  groceries:
    'Food and household supplies from supermarkets, markets and corner shops.',
  dining:
    'Food and drink prepared for you: restaurants, cafés, takeaway, delivery.',
  transport:
    'Getting around day to day: fuel, parking, tolls, public transport, taxis, car upkeep and car insurance.',
  utilities:
    'The household\'s recurring supply and connection bills: electricity, water, gas, internet, landline and mobile plans, TV, and services on them such as a water purifier rental.',
  housing:
    'The cost of the dwelling itself: rent or mortgage, building fees, property tax, home and appliance insurance, appliances fixed to the building such as an air conditioner or a water heater, the upkeep and repair of the home and its fixtures, garden and pool included, and services tied to the property such as cleaning or a security patrol.',
  health:
    'Care of body and mind: doctors, pharmacy, dental, glasses, therapy, the gym, health insurance.',
  insurance:
    'Insurance is filed by what it protects, so car, health, home and appliance policies go to transport, health and housing; only a policy with no such purpose, such as life insurance, or one whose purpose the statement does not tell, stays here.',
  education:
    'Schooling and learning: tuition, kindergarten, courses, study books, children\'s activities.',
  shopping:
    'Things you buy and keep: clothing, electronics, furniture, home goods, appliances that move with you.',
  entertainment:
    'Leisure: cinema, streaming, concerts, hobbies, games, sports events.',
  travel:
    'Trips away from home: flights, hotels, car hire, and spending abroad on a trip.',
  gifts:
    'Presents and donations.',
  other:
    'A real charge that fits no category: bank fees, transfers, fines.',
  uncategorized:
    'The card agent could not tell; the review asks the person.',
}
