*Problem Statement*

People often have limited free time but struggle to discover activities that match their interests, available hours, budget, and location. They must search across multiple platforms, compare options, and manually determine whether an activity is feasible. This leads to decision fatigue, excessive time spent planning, and sometimes abandoning plans altogether and staying at home, despite wanting to go out and explore.

Problem Vision

TimeWise helps users turn their available free time into personalized, realistic, and actionable plans within seconds by eliminating decision fatigue.

Value Proposition

"Less time deciding. More time experiencing." 

User Personas

Young Professionals: Find enjoyable activities after work or during weekends 
Couples: Discover experiences suited to shared interests and preferences 
Friend Groups: Find activities everyone can agree on without lengthy discussions 

 User Research Findings

Based on the primary research via 10+ interviews (telephonic and in-person) and secondary research through public discussions available on the internet and platforms like Reddit, below user pain points were identified - 

Decision fatigue and abandoned plans 
Users express a desire to do something enjoyable but struggle to decide what to do. Some end up scrolling, sleeping, or staying home instead. 
TimeWise opportunity: Provide a small set of relevant, actionable recommendations rather than an overwhelming list.
 
Repetitive activities and lack of variety 
Users repeatedly choose familiar options such as movies, restaurants, malls, and cafés, even when they want something different. 
TimeWise opportunity: Recommend diverse experiences, including familiar favorites, hobbies, workshops, outdoor activities, and at-home ideas, depending on the user's mood. 

Fragmented activity discovery 
Users rely on multiple channels, including Instagram, friends, search engines, and event platforms, to find things to do. 
TimeWise opportunity: Aggregate different activity categories into one personalized discovery experience. 

Budget and practical constraints 

Users want enjoyable activities but may be restricted by spending limits, transport availability, distance, or timing. 
TimeWise opportunity: Consider budget, duration, travel, and activity requirements before presenting recommendations. 

Different interests and social preferences 
People want activities suited to their social context, whether they are going alone, as a couple, or with friends. 
TimeWise opportunity: Personalize activities based on group type, shared interests, and preferred social experience. 

Academic Research Outcome: Research supports the broader premise that too many options can make decisions harder. A study published in Tourism Management found that larger choice sets could increase the likelihood of choosing nothing in its experimental tourism scenarios. A systematic review also explains that choice overload depends on the complexity of the decision and the characteristics of the decision-maker. (https://www.sciencedirect.com/science/article/abs/pii/S0261517712000921?utm_source=chatgpt.com) 
PM implication: TimeWise should optimize for decision completion, not simply the number of activities displayed. This supports testing a short, curated shortlist, although it does not prove that exactly five recommendations is the ideal number.
Product Success Metrics
North Star Metric: Number of recommended activities or plans that users accept
Other Metrics:
Time to choose an activity 
Recommendation relevance 
Plan selection rate 
Plan feasibility 
User satisfaction 





MVP Scope and Feature Prioritization

Define our MVP

Goal: Identify the minimum features needed to solve our core problem: helping users overcome decision fatigue and turn free time into actionable plans.

User Journey (v1): Tell us your mood & preferences -> Get Personalised Recommendations -> Choose & Follow a plan

Feature Prioritization using MoSCoW

Feature
Priority
Reason
Natural Processing Language Input
Must
User can express their preferences conversationally
Personalization 
Must
Core Personalization
Activity Discovery 
Must
Primary product value
Itinerary Planner
Should
Delighter
Regeneration & swap activities
Should
Improvise recommendations without restarting
Map and travel estimates
Should
Improve practical usability
Weather-aware suggestions 
Could
Weather-aware suggestions 
Shareable plans 
Could
Useful for couples and groups 
In-app ticket booking 
Won’t
Requires additional integrations 
Live cinema showtimes 
Won’t
Reliable data access is difficult 



MVP success criteria

We'll test the following targets with early users:
At least 60% select a recommended activity or plan.
Median decision time of under 5 minutes.
At least 80% find one recommendation relevant.



Finalized MVP Scope

Product decision: TimeWise will support both individual activity recommendations and complete multi-activity plans, based on what the user needs. 


Feature
Scope
Natural Processing Language Input
Users describe their mood, interests, or requirements 
Personalization
Location, budget, available time, group size, preferences 
Activity Discovery 
3–5 personalized activity recommendations 
Itinerary Planner 
2-3 complete itineraries
Regeneration & swap activities
View details, change preferences, regenerate suggestions 
Actionable Results 
Directions, relevant source links, estimated costs 


Launch strategy: Start with one Indian city and expand after validation. Support both at-home and out-of-home activities, with verified local data where required. 

Out of scope for V1: In-app bookings and payments, user accounts, advanced group coordination, and integrations requiring restricted ticketing APIs.

User Journey

User Input: User describes their mood, interests, or what they feel like doing. 
Understand Preferences: AI extracts location, budget, time, and company. It asks only for essential missing details. 
Generate Recommendations: AI generates list of feasible activities/ itineraries
Explore and refine: User switches modes, compares options, changes preferences, or requests alternatives 
Take Action: User selects an activity or plan and opens directions or relevant external links. 

UX Design

Single conversational entry point and non mandatory Dropdowns: No lengthy questionnaire before recommendations.
Hybrid mode: AI selects the starting mode, while users retain control.
Visual recommendations: Short cards instead of paragraphs of AI-generated text.
Minimal friction: Users can explore without signing up.
Transparent information: Show estimated costs and durations, and distinguish verified details from assumptions.
