import
  std/[random, sets, tables, options, strutils],
  fidget2/measure,
  common

const
  DepotTags = ["charger", "junction", "supply_depot"]
  HubTags = ["hub", "hub", "main_nexus"]
  StationTags = ["aligner_station", "scrambler_station", "miner_station", "scout_station"]
  ResourceNames = ["carbon", "oxygen", "germanium", "silicon"]
  ExploreSteps = 8
  DebugEnabled = false
  DebugEvery = 50
  DebugScramblerId = 0
  DebugAlignerId = 1
  DebugMinerId = 2

const Offsets4 = [
  Location(x: 1, y: 0),
  Location(x: 0, y: 1),
  Location(x: -1, y: 0),
  Location(x: 0, y: -1),
]

type
  PendingAction = enum
    PendingNone = 0,
    PendingAlign = 1,
    PendingScramble = 2

  CogsguardAlignAllAgent* = ref object
    agentId*: int
    cfg: Config
    random: Rand
    map: Table[Location, seq[FeatureValue]]
    seen: HashSet[Location]
    unreachables: HashSet[Location]
    location: Location
    bump: bool

    exploreDirIndex: int
    exploreSteps: int

    stations: Table[string, Location]
    depots: Table[Location, int] # -1 clips, 0 neutral/unknown, 1 cogs
    extractors: Table[string, seq[Location]]
    extractorRemaining: Table[Location, int]
    hub: Option[Location]
    chest: Option[Location]
    actionIds: Table[string, int]

    pendingAction: PendingAction
    pendingTarget: Option[Location]
    lastHeart: int
    stepCount: int

  CogsguardAlignAllPolicy* = ref object
    agents*: seq[CogsguardAlignAllAgent]

proc getVibeName(agent: CogsguardAlignAllAgent, vibeId: int): string =
  if vibeId >= 0 and vibeId < agent.cfg.vibeNames.len:
    return agent.cfg.vibeNames[vibeId]
  return "default"

proc getActionId(agent: CogsguardAlignAllAgent, name: string): int =
  return agent.actionIds.getOrDefault(name, agent.cfg.actions.noop)

proc actionForVibe(agent: CogsguardAlignAllAgent, vibe: string): int =
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

proc getAlignment(tagNames: HashSet[string], clipped: int): int =
  if "collective:cogs" in tagNames or "cogs" in tagNames:
    return 1
  if "collective:clips" in tagNames or "clips" in tagNames:
    return -1
  if clipped > 0:
    return -1
  return 0

proc isResourceExtractor(tagName: string): bool =
  for resource in ResourceNames:
    if resource & "_extractor" in tagName:
      return true
    if resource & "_chest" in tagName:
      return true
  return false

proc updateDiscoveries(agent: CogsguardAlignAllAgent, visible: Table[Location, seq[FeatureValue]]) =
  for location, features in visible:
    let tagNames = getTagNames(agent.cfg, features)
    if tagNames.len == 0:
      continue

    let absoluteLoc = Location(x: location.x + agent.location.x, y: location.y + agent.location.y)
    let clipped = featureValue(features, agent.cfg.features.clipped)
    let alignment = getAlignment(tagNames, clipped)

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

proc updateMap(agent: CogsguardAlignAllAgent, visible: Table[Location, seq[FeatureValue]]) {.measure.} =
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

proc moveTo(agent: CogsguardAlignAllAgent, target: Location): int =
  if agent.location == target:
    return agent.cfg.actions.noop
  let action = agent.cfg.aStar(agent.location, target, agent.map)
  if action.isSome():
    return action.get()
  if DebugEnabled and (agent.agentId == DebugScramblerId or agent.agentId == DebugAlignerId or agent.agentId == DebugMinerId) and agent.stepCount mod DebugEvery == 0:
    echo "[align-all] astar failed id=", agent.agentId,
      " loc=(", agent.location.x, ",", agent.location.y, ")",
      " target=(", target.x, ",", target.y, ")"
  return agent.cfg.actions.noop

proc stepAction(agent: CogsguardAlignAllAgent, fromLoc, toLoc: Location): int =
  if toLoc.x == fromLoc.x + 1 and toLoc.y == fromLoc.y:
    return agent.cfg.actions.moveEast
  if toLoc.x == fromLoc.x - 1 and toLoc.y == fromLoc.y:
    return agent.cfg.actions.moveWest
  if toLoc.y == fromLoc.y - 1 and toLoc.x == fromLoc.x:
    return agent.cfg.actions.moveNorth
  if toLoc.y == fromLoc.y + 1 and toLoc.x == fromLoc.x:
    return agent.cfg.actions.moveSouth
  return agent.cfg.actions.noop

proc explore(agent: CogsguardAlignAllAgent): int =
  let unseen = agent.cfg.getNearbyUnseen(agent.location, agent.map, agent.seen, agent.unreachables)
  if unseen.isSome():
    let action = agent.moveTo(unseen.get())
    if action != agent.cfg.actions.noop:
      return action
    agent.unreachables.incl(unseen.get())

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
  agent: CogsguardAlignAllAgent,
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

proc nearestDepot(agent: CogsguardAlignAllAgent, alignmentFilter: int): Option[Location] =
  var candidates: seq[Location] = @[]
  for loc, alignment in agent.depots:
    if alignment == alignmentFilter:
      candidates.add(loc)
  if candidates.len == 0:
    return none(Location)
  return agent.nearestLocation(candidates)

proc moveToOrExplore(agent: CogsguardAlignAllAgent, target: Option[Location]): int =
  if target.isSome():
    return agent.moveTo(target.get())
  return agent.explore()

proc returnToHubSearch(agent: CogsguardAlignAllAgent): int =
  if agent.hub.isSome():
    let hubLoc = agent.hub.get()
    if manhattan(agent.location, hubLoc) > 2:
      return agent.moveTo(hubLoc)
  return agent.explore()

proc nearestAlignedDepot(agent: CogsguardAlignAllAgent): Option[Location] =
  if agent.hub.isSome():
    return agent.hub
  return agent.nearestDepot(1)

proc doDeposit(agent: CogsguardAlignAllAgent): int =
  let depot = agent.nearestAlignedDepot()
  return agent.moveToOrExplore(depot)

proc doGather(agent: CogsguardAlignAllAgent): int =
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
  agent: CogsguardAlignAllAgent,
  cargo: int,
  invMiner: int
): int =
  if invMiner == 0:
    if "miner_station" in agent.stations:
      return agent.moveToOrExplore(some(agent.stations["miner_station"]))
    return agent.returnToHubSearch()

  let capacity = max(4, 40 * invMiner)
  if cargo >= capacity - 2:
    return agent.doDeposit()
  return agent.doGather()

proc roleForAgent(agentId: int): string =
  case agentId
  of 0:
    return "scrambler"
  of 1:
    return "aligner"
  of 2, 3, 4:
    return "miner"
  else:
    return "scout"

proc maybeMarkPending(
  agent: CogsguardAlignAllAgent,
  target: Location,
  actionKind: PendingAction,
  invHeart: int,
  action: int
) =
  if action == agent.cfg.actions.noop:
    return
  if manhattan(agent.location, target) == 1:
    agent.pendingAction = actionKind
    agent.pendingTarget = some(target)
    agent.lastHeart = invHeart

proc attemptAlign(
  agent: CogsguardAlignAllAgent,
  target: Location,
  invHeart: int
): int =
  if agent.location == target:
    return agent.explore()
  let action = agent.moveTo(target)
  agent.maybeMarkPending(target, PendingAlign, invHeart, action)
  return action

proc attemptScramble(
  agent: CogsguardAlignAllAgent,
  target: Location,
  invHeart: int
): int =
  if agent.location == target:
    return agent.explore()
  let action = agent.moveTo(target)
  agent.maybeMarkPending(target, PendingScramble, invHeart, action)
  return action

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
  agent: CogsguardAlignAllAgent,
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

    agent.stepCount += 1
    let visible = parseVisible(numTokens, sizeToken, rawObservation)
    agent.updateMap(visible)
    agent.updateDiscoveries(visible)

    let vibeId = agent.cfg.getVibe(visible, Location(x: 0, y: 0))
    let vibeName = agent.getVibeName(vibeId)

    let invHeart = agent.cfg.getInventory(visible, agent.cfg.features.invHeart)
    let invInfluence = agent.cfg.getInventory(visible, agent.cfg.features.invInfluence)
    let invAligner = agent.cfg.getInventory(visible, agent.cfg.features.invAligner)
    let invScrambler = agent.cfg.getInventory(visible, agent.cfg.features.invScrambler)
    let invMiner = agent.cfg.getInventory(visible, agent.cfg.features.invMiner)
    let invCarbon = agent.cfg.getInventory(visible, agent.cfg.features.invCarbon)
    let invOxygen = agent.cfg.getInventory(visible, agent.cfg.features.invOxygen)
    let invGermanium = agent.cfg.getInventory(visible, agent.cfg.features.invGermanium)
    let invSilicon = agent.cfg.getInventory(visible, agent.cfg.features.invSilicon)
    let cargo = invCarbon + invOxygen + invGermanium + invSilicon

    if agent.pendingAction != PendingNone and invHeart < agent.lastHeart:
      if agent.pendingTarget.isSome():
        let target = agent.pendingTarget.get()
        if agent.pendingAction == PendingAlign:
          agent.depots[target] = 1
        elif agent.pendingAction == PendingScramble:
          agent.depots[target] = 0
      agent.pendingAction = PendingNone
      agent.pendingTarget = none(Location)

    agent.lastHeart = invHeart

    var action = agent.cfg.actions.noop

    let targetScramble = agent.nearestDepot(-1)
    let targetAlign = agent.nearestDepot(0)
    let role = roleForAgent(agent.agentId)

    if DebugEnabled and (agent.agentId == DebugScramblerId or agent.agentId == DebugAlignerId or agent.agentId == DebugMinerId) and agent.stepCount mod DebugEvery == 0:
      var clipsDepots = 0
      var neutralDepots = 0
      var cogsDepots = 0
      for _, alignment in agent.depots:
        if alignment == -1:
          clipsDepots += 1
        elif alignment == 0:
          neutralDepots += 1
        elif alignment == 1:
          cogsDepots += 1
      let hasScramblerStation = "scrambler_station" in agent.stations
      let hasAlignerStation = "aligner_station" in agent.stations
      let hasMinerStation = "miner_station" in agent.stations
      let chestDist = if agent.chest.isSome(): manhattan(agent.location, agent.chest.get()) else: -1
      let hubDist = if agent.hub.isSome(): manhattan(agent.location, agent.hub.get()) else: -1
      let minerCapacity = max(4, 40 * invMiner)
      echo "[align-all] step=", agent.stepCount,
        " id=", agent.agentId,
        " role=", role,
        " vibe=", vibeName,
        " loc=(", agent.location.x, ",", agent.location.y, ")",
        " heart=", invHeart,
        " infl=", invInfluence,
        " gearA=", invAligner,
        " gearS=", invScrambler,
        " gearM=", invMiner,
        " cargo=", cargo, "/", minerCapacity,
        " depots=", clipsDepots, "/", neutralDepots, "/", cogsDepots,
        " chest=", agent.chest.isSome(),
        " hub=", agent.hub.isSome(),
        " stations(a/s/m)=", hasAlignerStation, "/", hasScramblerStation, "/", hasMinerStation,
        " dist(chest/hub)=", chestDist, "/", hubDist,
        " targetA=", targetAlign.isSome(),
        " targetS=", targetScramble.isSome()

    if role == "scrambler":
      if vibeName != "scrambler":
        action = agent.actionForVibe("scrambler")
      elif invScrambler == 0:
        if "scrambler_station" in agent.stations:
          action = agent.moveToOrExplore(some(agent.stations["scrambler_station"]))
        else:
          action = agent.returnToHubSearch()
      elif invHeart == 0:
        if agent.chest.isSome():
          action = agent.moveToOrExplore(agent.chest)
        else:
          action = agent.returnToHubSearch()
      elif targetScramble.isSome():
        action = agent.attemptScramble(targetScramble.get(), invHeart)
      else:
        action = agent.explore()
    elif role == "aligner":
      if vibeName != "aligner":
        action = agent.actionForVibe("aligner")
      elif invAligner == 0:
        if "aligner_station" in agent.stations:
          action = agent.moveToOrExplore(some(agent.stations["aligner_station"]))
        else:
          action = agent.returnToHubSearch()
      elif invHeart == 0:
        if agent.chest.isSome():
          action = agent.moveToOrExplore(agent.chest)
        else:
          action = agent.returnToHubSearch()
      elif invInfluence == 0:
        if agent.hub.isSome():
          action = agent.moveToOrExplore(agent.hub)
        else:
          action = agent.returnToHubSearch()
      elif targetAlign.isSome():
        action = agent.attemptAlign(targetAlign.get(), invHeart)
      else:
        action = agent.explore()
    elif role == "miner":
      if vibeName != "miner":
        action = agent.actionForVibe("miner")
      else:
        action = agent.actMiner(cargo, invMiner)
    else:
      if vibeName != "scout":
        action = agent.actionForVibe("scout")
      else:
        action = agent.explore()

    agentAction[] = action.int32
  except:
    echo getCurrentException().getStackTrace()
    echo getCurrentExceptionMsg()
    quit()

proc newCogsguardAlignAllAgent*(agentId: int, environmentConfig: string): CogsguardAlignAllAgent =
  var config = parseConfig(environmentConfig)
  result = CogsguardAlignAllAgent(agentId: agentId, cfg: config)
  result.random = initRand(agentId)
  result.map = initTable[Location, seq[FeatureValue]]()
  result.seen = initHashSet[Location]()
  result.unreachables = initHashSet[Location]()
  result.location = Location(x: 0, y: 0)
  result.exploreDirIndex = 0
  result.exploreSteps = 0
  result.stations = initTable[string, Location]()
  result.depots = initTable[Location, int]()
  result.extractors = initTable[string, seq[Location]]()
  result.extractorRemaining = initTable[Location, int]()
  result.hub = none(Location)
  result.chest = none(Location)
  result.actionIds = initTable[string, int]()
  for id, name in config.config.actions:
    result.actionIds[name] = id
  result.pendingAction = PendingNone
  result.pendingTarget = none(Location)
  result.lastHeart = 0
  result.stepCount = 0

proc newCogsguardAlignAllPolicy*(environmentConfig: string): CogsguardAlignAllPolicy =
  let cfg = parseConfig(environmentConfig)
  var agents: seq[CogsguardAlignAllAgent] = @[]
  for id in 0 ..< cfg.config.numAgents:
    agents.add(newCogsguardAlignAllAgent(id, environmentConfig))
  CogsguardAlignAllPolicy(agents: agents)

proc stepBatch*(
  policy: CogsguardAlignAllPolicy,
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
