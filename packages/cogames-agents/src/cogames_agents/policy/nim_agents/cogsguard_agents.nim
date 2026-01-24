import
  std/[random, sets, tables, options, strutils],
  fidget2/measure,
  common

const
  CargoBase = 4
  CargoPerMiner = 40
  ExploreSteps = 8
  RoleNames = ["miner", "scout", "aligner", "scrambler"]
  DepotTags = ["charger", "junction", "supply_depot"]
  HubTags = ["hub", "assembler", "main_nexus"]
  StationTags = ["miner_station", "scout_station", "aligner_station", "scrambler_station"]
  ResourceNames = ["carbon", "oxygen", "germanium", "silicon"]

const Offsets4 = [
  Location(x: 1, y: 0),
  Location(x: 0, y: 1),
  Location(x: -1, y: 0),
  Location(x: 0, y: -1),
]

type
  CogsguardAgent* = ref object
    agentId*: int
    cfg: Config
    random: Rand
    map: Table[Location, seq[FeatureValue]]
    seen: HashSet[Location]
    unreachables: HashSet[Location]
    location: Location
    lastActions: seq[int]
    bump: bool

    exploreDirIndex: int
    exploreSteps: int

    stations: Table[string, Location]
    extractors: Table[string, seq[Location]]
    extractorRemaining: Table[Location, int]
    depots: Table[Location, int] # -1 clips, 0 neutral/unknown, 1 cogs
    hub: Option[Location]
    chest: Option[Location]

    actionIds: Table[string, int]

  CogsguardPolicy* = ref object
    agents*: seq[CogsguardAgent]

proc getVibeName(agent: CogsguardAgent, vibeId: int): string =
  if vibeId >= 0 and vibeId < agent.cfg.vibeNames.len:
    return agent.cfg.vibeNames[vibeId]
  return "default"

proc getActionId(agent: CogsguardAgent, name: string): int =
  return agent.actionIds.getOrDefault(name, agent.cfg.actions.noop)

proc actionForVibe(agent: CogsguardAgent, vibe: string): int =
  let actionName = "change_vibe_" & vibe
  return agent.getActionId(actionName)

proc featureValue(
  features: seq[FeatureValue],
  featureId: int
): int =
  for feature in features:
    if feature.featureId == featureId:
      return feature.value
  return -1

proc getTagNames(cfg: Config, features: seq[FeatureValue]): HashSet[string] =
  result = initHashSet[string]()
  for feature in features:
    if feature.featureId == cfg.features.tag:
      if feature.value >= 0 and feature.value < cfg.config.tags.len:
        result.incl(cfg.config.tags[feature.value])

proc getAlignment(tagNames: HashSet[string]): int =
  if "collective:cogs" in tagNames:
    return 1
  if "collective:clips" in tagNames:
    return -1
  return 0

proc isResourceExtractor(tagName: string): bool =
  for resource in ResourceNames:
    if resource & "_extractor" in tagName:
      return true
    if resource & "_chest" in tagName:
      return true
  return false

proc updateDiscoveries(agent: CogsguardAgent, visible: Table[Location, seq[FeatureValue]]) =
  for location, features in visible:
    let tagNames = getTagNames(agent.cfg, features)
    if tagNames.len == 0:
      continue

    let absoluteLoc = Location(x: location.x + agent.location.x, y: location.y + agent.location.y)
    let alignment = getAlignment(tagNames)

    for tagName in tagNames.items:
      for stationName in StationTags.items:
        if tagName == stationName:
          agent.stations[stationName] = absoluteLoc
      if tagName in HubTags:
        agent.hub = some(absoluteLoc)
      if tagName in DepotTags:
        agent.depots[absoluteLoc] = alignment

      if tagName == "chest" and not tagName.isResourceExtractor():
        agent.chest = some(absoluteLoc)

      if tagName.isResourceExtractor():
        for resource in ResourceNames:
          if resource & "_extractor" in tagName or resource & "_chest" in tagName:
            var locations = agent.extractors.getOrDefault(resource, @[])
            if absoluteLoc notin locations:
              locations.add(absoluteLoc)
            agent.extractors[resource] = locations

            let remaining = featureValue(features, agent.cfg.features.remainingUses)
            if remaining != -1:
              agent.extractorRemaining[absoluteLoc] = remaining

proc updateMap(agent: CogsguardAgent, visible: Table[Location, seq[FeatureValue]]) {.measure.} =
  if agent.map.len == 0:
    agent.map = visible
    agent.location = Location(x: 0, y: 0)
    for x in -5 .. 5:
      for y in -5 .. 5:
        agent.seen.incl(Location(x: x, y: y))
    return

  var newLocation = agent.location
  let lastAction = agent.cfg.getLastAction(visible)
  if lastAction == agent.cfg.actions.moveNorth:
    newLocation.y -= 1
  elif lastAction == agent.cfg.actions.moveSouth:
    newLocation.y += 1
  elif lastAction == agent.cfg.actions.moveWest:
    newLocation.x -= 1
  elif lastAction == agent.cfg.actions.moveEast:
    newLocation.x += 1

  block bumpCheck:
    agent.bump = false
    for x in -5 .. 5:
      for y in -5 .. 5:
        let visibleLocation = Location(x: x, y: y)
        let mapLocation = Location(x: x + newLocation.x, y: y + newLocation.y)
        if mapLocation notin agent.seen:
          continue
        var visibleTag = agent.cfg.getTag(visible, visibleLocation)
        if visibleTag == agent.cfg.tags.agent:
          visibleTag = -1
        var mapTag = agent.cfg.getTag(agent.map, mapLocation)
        if mapTag == agent.cfg.tags.agent:
          mapTag = -1
        if visibleTag != mapTag:
          newLocation = agent.location
          agent.bump = true
          break bumpCheck

  agent.location = newLocation
  for x in -5 .. 5:
    for y in -5 .. 5:
      let visibleLocation = Location(x: x, y: y)
      let mapLocation = Location(x: x + agent.location.x, y: y + agent.location.y)
      agent.map[mapLocation] = visible.getOrDefault(visibleLocation, @[])
      agent.seen.incl(mapLocation)

proc moveTo(agent: CogsguardAgent, target: Location): int =
  if agent.location == target:
    return agent.cfg.actions.noop
  let action = agent.cfg.aStar(agent.location, target, agent.map)
  if action.isSome():
    return action.get()
  return agent.cfg.actions.noop

proc stepAction(agent: CogsguardAgent, fromLoc, toLoc: Location): int =
  if toLoc.x == fromLoc.x + 1 and toLoc.y == fromLoc.y:
    return agent.cfg.actions.moveEast
  if toLoc.x == fromLoc.x - 1 and toLoc.y == fromLoc.y:
    return agent.cfg.actions.moveWest
  if toLoc.y == fromLoc.y - 1 and toLoc.x == fromLoc.x:
    return agent.cfg.actions.moveNorth
  if toLoc.y == fromLoc.y + 1 and toLoc.x == fromLoc.x:
    return agent.cfg.actions.moveSouth
  return agent.cfg.actions.noop

proc explore(agent: CogsguardAgent): int =
  if agent.exploreSteps < ExploreSteps:
    let offset = Offsets4[agent.exploreDirIndex]
    let nextLoc = agent.location + offset
    if agent.cfg.isWalkable(agent.map, nextLoc):
      agent.exploreSteps += 1
      return agent.stepAction(agent.location, nextLoc)

  for i in 1 .. 4:
    let idx = (agent.exploreDirIndex + i) mod 4
    let offset = Offsets4[idx]
    let nextLoc = agent.location + offset
    if agent.cfg.isWalkable(agent.map, nextLoc):
      agent.exploreDirIndex = idx
      agent.exploreSteps = 1
      return agent.stepAction(agent.location, nextLoc)

  return agent.cfg.actions.noop

proc nearestLocation(
  agent: CogsguardAgent,
  locations: seq[Location]
): Option[Location] =
  var bestDist = high(int)
  var best: Option[Location] = none(Location)
  for loc in locations:
    let dist = manhattan(agent.location, loc)
    if dist < bestDist:
      bestDist = dist
      best = some(loc)
  return best

proc nearestDepot(agent: CogsguardAgent, alignmentFilter: int): Option[Location] =
  var candidates: seq[Location] = @[]
  if alignmentFilter == 1 and agent.hub.isSome():
    candidates.add(agent.hub.get())

  for loc, alignment in agent.depots:
    if alignmentFilter == 0:
      if alignment == 0:
        candidates.add(loc)
    elif alignment == alignmentFilter:
      candidates.add(loc)

  if candidates.len == 0:
    return none(Location)
  return agent.nearestLocation(candidates)

proc getGear(agent: CogsguardAgent, stationName: string): int =
  if stationName notin agent.stations:
    return agent.explore()
  let stationLoc = agent.stations.getOrDefault(stationName, agent.location)
  return agent.moveTo(stationLoc)

proc doDeposit(agent: CogsguardAgent): int =
  let depot = agent.nearestDepot(1)
  if depot.isSome():
    return agent.moveTo(depot.get())
  if agent.hub.isSome():
    return agent.moveTo(agent.hub.get())
  return agent.explore()

proc doGather(agent: CogsguardAgent): int =
  var candidates: seq[Location] = @[]
  for resource in ResourceNames:
    for loc in agent.extractors.getOrDefault(resource, @[]):
      let remaining = agent.extractorRemaining.getOrDefault(loc, 1)
      if remaining != 0:
        candidates.add(loc)

  if candidates.len == 0:
    return agent.explore()

  let target = agent.nearestLocation(candidates)
  if target.isSome():
    return agent.moveTo(target.get())
  return agent.explore()

proc actMiner(
  agent: CogsguardAgent,
  cargo: int,
  invMiner: int
): int =
  if invMiner == 0:
    return agent.getGear("miner_station")

  let capacity = max(CargoBase, CargoPerMiner * invMiner)
  if cargo >= capacity - 2:
    return agent.doDeposit()

  return agent.doGather()

proc actScout(agent: CogsguardAgent, invScout: int): int =
  if invScout == 0:
    return agent.getGear("scout_station")

  let unseen = agent.cfg.getNearbyUnseen(agent.location, agent.map, agent.seen, agent.unreachables)
  if unseen.isSome():
    return agent.moveTo(unseen.get())
  return agent.explore()

proc actAligner(agent: CogsguardAgent, invAligner: int, hearts: int): int =
  if invAligner == 0:
    return agent.getGear("aligner_station")
  if hearts == 0:
    if agent.chest.isSome():
      return agent.moveTo(agent.chest.get())
    return agent.explore()

  let target = agent.nearestDepot(0)
  if target.isSome():
    return agent.moveTo(target.get())
  return agent.explore()

proc actScrambler(agent: CogsguardAgent, invScrambler: int, hearts: int): int =
  if invScrambler == 0:
    return agent.getGear("scrambler_station")
  if hearts == 0:
    if agent.chest.isSome():
      return agent.moveTo(agent.chest.get())
    return agent.explore()

  let target = agent.nearestDepot(-1)
  if target.isSome():
    return agent.moveTo(target.get())
  return agent.explore()

proc parseVisible(
  numTokens: int,
  sizeToken: int,
  rawObservation: pointer
): Table[Location, seq[FeatureValue]] =
  let observations = cast[ptr UncheckedArray[uint8]](rawObservation)
  for token in 0 ..< numTokens:
    let locationPacked = observations[token * sizeToken]
    let featureId = observations[token * sizeToken + 1]
    let value = observations[token * sizeToken + 2]
    if locationPacked == 255 and featureId == 255 and value == 255:
      break
    var location: Location
    if locationPacked != 0xFF:
      location.y = (locationPacked shr 4).int - 5
      location.x = (locationPacked and 0x0F).int - 5
    if location notin result:
      result[location] = @[]
    result[location].add(FeatureValue(featureId: featureId.int, value: value.int))

proc step*(
  agent: CogsguardAgent,
  numAgents: int,
  numTokens: int,
  sizeToken: int,
  rawObservation: pointer,
  numActions: int,
  agentAction: ptr int32
) {.measure.} =
  try:
    discard numAgents
    discard numActions

    let visible = parseVisible(numTokens, sizeToken, rawObservation)
    agent.updateMap(visible)
    agent.updateDiscoveries(visible)

    let vibeId = agent.cfg.getVibe(visible, Location(x: 0, y: 0))
    let vibeName = agent.getVibeName(vibeId)

    let invCarbon = agent.cfg.getInventory(visible, agent.cfg.features.invCarbon)
    let invOxygen = agent.cfg.getInventory(visible, agent.cfg.features.invOxygen)
    let invGermanium = agent.cfg.getInventory(visible, agent.cfg.features.invGermanium)
    let invSilicon = agent.cfg.getInventory(visible, agent.cfg.features.invSilicon)
    let invHeart = agent.cfg.getInventory(visible, agent.cfg.features.invHeart)
    let invMiner = agent.cfg.getInventory(visible, agent.cfg.features.invMiner)
    let invScout = agent.cfg.getInventory(visible, agent.cfg.features.invScout)
    let invAligner = agent.cfg.getInventory(visible, agent.cfg.features.invAligner)
    let invScrambler = agent.cfg.getInventory(visible, agent.cfg.features.invScrambler)
    let cargo = invCarbon + invOxygen + invGermanium + invSilicon

    var action = agent.cfg.actions.noop

    if vibeName == "gear":
      let choice = agent.random.rand(0 ..< RoleNames.len)
      action = agent.actionForVibe(RoleNames[choice])
    elif vibeName == "miner":
      action = agent.actMiner(cargo, invMiner)
    elif vibeName == "scout":
      action = agent.actScout(invScout)
    elif vibeName == "aligner":
      action = agent.actAligner(invAligner, invHeart)
    elif vibeName == "scrambler":
      action = agent.actScrambler(invScrambler, invHeart)
    else:
      action = agent.cfg.actions.noop

    agentAction[] = action.int32
  except:
    echo getCurrentException().getStackTrace()
    echo getCurrentExceptionMsg()
    quit()

proc newCogsguardAgent*(agentId: int, environmentConfig: string): CogsguardAgent =
  var config = parseConfig(environmentConfig)
  result = CogsguardAgent(agentId: agentId, cfg: config)
  result.random = initRand(agentId)
  result.map = initTable[Location, seq[FeatureValue]]()
  result.seen = initHashSet[Location]()
  result.unreachables = initHashSet[Location]()
  result.location = Location(x: 0, y: 0)
  result.lastActions = @[]
  result.exploreDirIndex = 0
  result.exploreSteps = 0
  result.stations = initTable[string, Location]()
  result.extractors = initTable[string, seq[Location]]()
  result.extractorRemaining = initTable[Location, int]()
  result.depots = initTable[Location, int]()
  result.hub = none(Location)
  result.chest = none(Location)
  result.actionIds = initTable[string, int]()

  for id, name in config.config.actions:
    result.actionIds[name] = id

proc newCogsguardPolicy*(environmentConfig: string): CogsguardPolicy =
  let cfg = parseConfig(environmentConfig)
  var agents: seq[CogsguardAgent] = @[]
  for id in 0 ..< cfg.config.numAgents:
    agents.add(newCogsguardAgent(id, environmentConfig))
  CogsguardPolicy(agents: agents)

proc stepBatch*(
  policy: CogsguardPolicy,
  agentIds: pointer,
  numAgentIds: int,
  numAgents: int,
  numTokens: int,
  sizeToken: int,
  rawObservations: pointer,
  numActions: int,
  rawActions: pointer
) =
  let ids = cast[ptr UncheckedArray[int32]](agentIds)
  let obsArray = cast[ptr UncheckedArray[uint8]](rawObservations)
  let actionArray = cast[ptr UncheckedArray[int32]](rawActions)
  let obsStride = numTokens * sizeToken

  for i in 0 ..< numAgentIds:
    let idx = int(ids[i])
    let obsPtr = cast[pointer](obsArray[idx * obsStride].addr)
    let actPtr = cast[ptr int32](actionArray[idx].addr)
    step(policy.agents[idx], numAgents, numTokens, sizeToken, obsPtr, numActions, actPtr)
