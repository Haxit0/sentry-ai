export type ScenarioPresentation = {
  label:string;
  group:"Delivery plans"|"Check information";
  mode:"delay"|"on-time"|"budget"|"capacity"|"reports"|"message";
  heading:string;
  intro:string;
  action:string;
  preview:string;
  working:string;
  context:string;
};

const scenarios:Record<string,ScenarioPresentation> = {
  "alpha-delay": {label:"Delivery is five days late",group:"Delivery plans",mode:"delay",heading:"How late is the delivery?",intro:"Adjust the delay, or keep the example and continue.",action:"Find my best option",preview:"Just compare costs, without AI",working:"Finding the best recovery option",context:"Delivery recovery"},
  "no-delay": {label:"Delivery is on time",group:"Delivery plans",mode:"on-time",heading:"Is any extra action needed?",intro:"Start with no added delay, or test what happens if that changes.",action:"Check if action is needed",preview:"Just compare costs, without AI",working:"Checking whether extra action is needed",context:"On-time delivery check"},
  "long-delay": {label:"Delivery is a month late",group:"Delivery plans",mode:"delay",heading:"What can recover a long delay?",intro:"Compare waiting, speeding up delivery and using another supplier.",action:"Find a long-delay recovery",preview:"Just compare costs, without AI",working:"Comparing recovery plans for the long delay",context:"Long-delay recovery"},
  "limited-capacity": {label:"Backup stock cannot cover every order",group:"Delivery plans",mode:"capacity",heading:"How much backup stock is available?",intro:"Check how limited backup stock affects costs and late orders.",action:"Check the backup capacity",preview:"Just compare costs, without AI",working:"Checking capacity and remaining lateness",context:"Limited backup stock"},
  "budget-blocked": {label:"Recovery must fit a budget and deadline",group:"Delivery plans",mode:"budget",heading:"What are your recovery limits?",intro:"Set your spending limit and how much lateness you can accept.",action:"Find an option within my budget",preview:"Just compare costs, without AI",working:"Comparing options within your limits",context:"Budget and deadline check"},
  "conflicting-eta": {label:"Supplier and carrier give different dates",group:"Check information",mode:"reports",heading:"Let's check the arrival reports.",intro:"Compare the source updates before choosing a recovery plan.",action:"Check these reports",preview:"Preview reports, without AI",working:"Checking the conflicting arrival estimates",context:"Conflicting arrival estimates"},
  "stale-update": {label:"Arrival updates are out of date",group:"Check information",mode:"reports",heading:"Are these arrival updates still reliable?",intro:"Check what needs refreshing before choosing a recovery plan.",action:"Check the old updates",preview:"Preview reports, without AI",working:"Checking whether the arrival updates are current",context:"Arrival update check"},
  "injected-note": {label:"A supplier message needs checking",group:"Check information",mode:"message",heading:"Can we trust this supplier message?",intro:"Check the message against the evidence before following its advice.",action:"Check the supplier message",preview:"Preview costs without checking the message",working:"Checking the message against source evidence",context:"Supplier message check"},
};

export function scenarioPresentation(id:string,fallback?:string):ScenarioPresentation {
  return scenarios[id]??{...scenarios["alpha-delay"],label:fallback??"Delivery planning"};
}
