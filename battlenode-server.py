#!/usr/bin/env python

import random
from collections import defaultdict

VERSION = 0.1

class Player:
    def __init__(self, name, beginnode):
        self.name = name
        self.beginnode = beginnode
        self.time = 0

    def __hash__(self):
        return hash(self.name)

    def tick(self):
        self.time = time + 1

class NodeType:
    def __init__(self, id, label, description, resistance, consumption, vision, buildduration, resistancemodifier=1, hidden=False):
        self.id = id
        self.label = label
        self.description = description
        self.resistance = resistance
        self.consumption = consumption #power consumption
        self.vision = vision
        self.buildduration = buildduration #in turns
        self.resistancemodifier = resistancemodifier
        self.hidden = hidden #doubles power consumption

class Event:
    def __init__(self, id, label, priority):
        self.id = id
        self.label = label
        self.priority = priority


class NonNeighbourLink(Exception):
    pass

class NotEnoughPower(Exception):
    pass

nodetypes = {
    'unspecialised':  NodeType('unspecialised',"Unspecialised node","A regular unspecialised node", 1, 10, 1,1,1),
    'shield':  NodeType('shield',"Shielded node","Shielded nodes are hardened nodes and are more resistant to enemy takeover", 5, 50, 1, 2, 1),
    'sabotage':  NodeType('sabotage',"Sabotage node","Sabotage nodes halve the resistance of incoming enemy nodes and have fairly high resistance themselves. Good for instant counterattacks.", 4, 200, 1, 3, 0.5),
    'attack':  NodeType('attack',"Attack node","Attack nodes halve the resistance of enemy nodes you link to, and have moderate resistance themselves.", 3, 150, 1, 2, 0.5),
    'corruption':  NodeType('corruption',"Corruption node","Corruption nodes irreversibly poison their own subgrid when assimilated by the enemy, making the spot cost power instead of yield power and making it very undesireable to own", 0, 200, 1, 3,1 ),
    'destructor':  NodeType('destructor',"Destruction node","Destroys any specialisation on neighbouring enemy nodes when an attempt to assimilate it is made", 2, 200, 1, 3,1 ),
    'sensor':  NodeType('sensor',"Sensor node","Sensor nodes provide an enhanced field of vision", 2, 100, 3, 2, 1 ),
    'core':  NodeType('core',"Core node","Core nodes enable you to regulate your network's power flow. Without a core node, the whole network falls apart. They are veritable but power-hungry fortresses of resistance and they double the resistance of linked neighbouring nodes", 20, 1000, 1, 10, 2),
    'collaborator':  NodeType('collaborator',"Collaborator node","Feeds power to other players, outgoing connections from the collaborator are never assimilations but give power away and thus allow the formation of alliances and conspiracies", 1, 200, 1, 1, 1 ),
}

events = {
    'lostnode': Event('lostnode', "Node was lost due to insufficient power!",2),
    'lostcloak': Event('lostcloak', "Node lost its cloak due to insufficient power!",3),
    'lostspec': Event('lostspec', "Node lost its specialisation due to insufficient power!",4),
    'lostassimilated': Event('lostassimilated', "Node was taken over by the enemy!",1),
    'assimilatesuccess': Event('assimilatesuccess', "Node succesfully assimilated!",5),
    'powerincrease': Event('powerincrease', "Node received more energy",7),
    'powerdecrease': Event('powerdecrease', "Node now has less energy",6),
    'corruption': Event('corruption', "Corruption took place! The subgrid got poisoned!",1),
    'destruction': Event('destruction', "Your specialisation was destroyed!",1),
}

#whether a node will specialise or not is dependent on its power, if it specialises, it does so according to thes probabilities:
seed_defaultspecprobs = {
    (0.8, nodetypes['shield']),
    (0.1, nodetypes['sabotage']),
    (0.05, nodetypes['destructor']),
    (0.04, nodetypes['corruption']),
}
seed_defaulthideprob = 0.02
seed_defaulthideprob_spec = 0.25
seed_defaulthighpowerprob = 0.02
seed_defaultnonodeprob = 0.16
seed_defaultbeginpower = 2000

class Game:
    def __init__(self, name, width, height, seed_beginpower, seed_defaultbeginpower, seed_nonodeprob=seed_defaultnonodeprob, seed_specprobs=defaultspecseedprobs, seed_hideprob=seed_defaulthideprob, seed_hideprob_spec = seed_defaulthideprob_spec, seed_highpowerprob = seed_defaulthighpowerprob):
        self.name = name
        self.width = width
        self.height = height
        self.players = []
        self.nodes =  defaultdict(dict) # x => y => Node
        self.time = 0
        self.createnodes(seed_nonodeprob, seed_specprobs, seed_highpowerprob, seed_hideprob, seed_hideprob_spec)

        #self.changednodes = set() #will hold all changed nodes after a tick, needed to update clients
        self.visiblenodes = defaultdict(set) #will hold all visible nodes for each player
        self.waiting = [] #list of players that need to complete their turn still

    def __iter__(self):
        for d in nodes.values():
            for node in d.values():
                yield nodes

    def makebeginnode(self, seed_beginpower):
        valid = False
        while not valid:
            node = random.choice(iter(self))
            neighbours = list(node.neighbours())
            if len(neighbours) < 6:
                continue

            node.type = nodetypes['core']
            node.power = seed_beginpower
            valid = True


    def addplayer(self, name):
        beginnode = self.makebeginnode(seed_defaultbeginpower)
        player = Player(name, beginnode)
        self.players.append(player)


    def createnodes(self, seed_nonodeprob, seed_specprobs, seed_highpowerprod, seed_hideprob, seed_hideprob_spec):
        for x in range(1,self.width+1):
            for y in range(1,self.height+1):
                if random.random() <= seed_nonodeprob:
                    continue

                power = random.expovariate(1)*10 #exponential distribution
                if random.random() <= seed_highpowerprob: #chance for a extra high power node
                    power = power * power #square


                hidden = (random.random() < seed_hideprob)

                type = nodetypes['unspecialised']
                hidden = False
                if power > 0:
                    specprob = 1/power
                    if random.random() <= specprob:
                        hidden = (random.random() < seed_hideprob_spec)
                        r = random.random()
                        for prob, t in seedprobs:
                            if r <= summed + t:
                                type = t
                                break
                            summed += t


                self.nodes[x][y] = Node(self, x, y, type, None, power, 0, hidden)

    def tick(self):
        #check if all players are synced
        self.waiting = []
        for player in self.players:
            if player.time < game.time:
                self.waiting.append(player)

        #one time tick (turn)
        self.visiblenodes = defaultdict(set)
        for node in self:
            node.tick()
            if node.owner:
                self.visiblenodes[node.owner] |= node.visiblenodes()

    def post(self, player, content):
        #parse json content
        content = json.loads(content)
        if not 'command' in content:
            raise CommunicationError("No command in content")
        if not 'args' in content:
            raise CommunicationError("No arguments in content")
        if not 'version' in content:
            raise CommunicationError("No version in content")
        command = content['command']
        args = content['args']

        if command == 'link':



        parsedargs = []
        for a in args:
            if isinstance(a, str) and a[:4] == 'node':
                try:
                    x, y = a[4:].split('_')
                    x = int(x)
                    y = int(y)
                except:
                    raise CommunicationError("Error parsing node specification: " + a)

                parsedargs.append
            else:
                parsedargs.append(a)





    def playerdone(self):
        player.tick()

    def get(self, player):
        #HTTP get status

        if self.waiting:


        else:

        while player.time < game.time:
            player.tick()




class Link:
    def __init__(self, source, target, power):
           self.source = source
           self.target = target
           self.power = power

    def __eq__(self, other):
        return (self.source == other.source and self.target == other.target and self.power == other.power)


class Node:
    def __init__(self, game, x, y, type, owner, power, buildtime, hidden):
        self.game = game
        self.x = x
        self.y = y
        self.type = type
        self.power = power #subgrid power
        self.outlinks = []
        self.inlinks = []
        self.owner = owner
        self.buildtime = buildtime #from what time on is this node built? (may be in future, node will then be in a reconfigure mode and acts as a normal node until done)
        self.hidden = hidden

    def link(self, targetnode, power):
        if targetnode.x == self.x and targetnode.y == self.y:
           raise NonNeighbourLink()
        if abs(targetnode.x - self.x) > 1 or abs(targetnode.y - self.y) > 1:
           raise NonNeighbourLink()

       for link in outlinks:
           if link.target == targetnode: #update existing link
               link.power += power
               link.target.setevent(events['powerincrease'])
               return True


       for i, link in enumerate(inlinks):
           if link.source == targetnode and link.source.owner == self.owner: #conflicting reverse link
               if power < link.power:
                    link.power -= power
                    return True
               else:
                   power -= link.power
                   #deletion
                   link.source.inlinks.remove(link)
                   del self.inlinks[i]
                   return True

        link = Link(self, targetnode, power )
        self.outlinks.append(link)
        self.targetnode.inlinks.append(link)

    def hide(self):
        if self.energy - self.type.consumption <= 0:
            raise NotEnoughPower()
        else:
            self.hidden = True


    def energy(self):
        if self.hidden:
            energy = self.power - (self.type.consumption * 2)
        else:
            energy = self.power - self.type.consumption
        for link in self.outlinks:
            if link.owner == self.owner or self.type == nodetypes['collaborator']:
                energy = energy - self.link.power
        for link in self.inlinks:
            if link.owner == self.owner or self.type == nodetypes['collaborator']:
                energy = energy + self.link.power
        return energy

    def strength(self):
        if self.specialising():
            return self.energy()
        else:

        if self.specialising():
            resistance = 1
        else:
            resistance = self.resistance
        #check for sabotaging neighbours
        for link in self.outlinks:
            if link.target.type == nodetypes['sabotage'] and link.target.owner != self.owner and not link.target.specialising():
                resistance = resistance * link.target.resistancemodifier
        #check for neighbouring enemy attack nodes (or friendly core nodes)
        for link in self.inlinks:
            if (link.source.type == nodetypes['attack'] and link.source.owner != self.owner and not link.source.specialising()) or (link.source.type == nodetypes['core'] and link.target.owner == self.owner and not link.source.specialising()):
                resistance = resistance * link.target.resistancemodifier

        return resistance * self.energy()

    def specialise(self, type):
        #check whether enough energy
        if self.energy + self.type.consumption - type.consumption <= 0:
            raise NotEnoughPower()

        self.type = type
        self.buildtime = self.gametime + self.type.buildduration

    def specialising(self):
        #is the node currently specialising into something else?
        return self.buildtime > self.game.time


    def onassimilation(self, attacker):
        self.setevent(events["assimilatesuccess"])
        if self.type == nodetype['corruption']:
            if self.power > 0: #can't reverse corruptions
                self.power = -1 * self.power
                self.tick() #no extra tick, node may be lost again
                self.setevent(events["corruption"])
        elif self.type == 'destructor':
            for link in self.inlinks:
                if link.owner == attacker:
                    if link.source.type != nodetypes['unspecialised']:
                        link.source.type = nodetypes['unspecialised']
        self.type = nodetypes['unspecialised']
        self.hidden = False


    def tick(self):
        if node.type is None:
            return False

        #Check ownership

        #is an enemy attack in progress? If multiple attackers, the strongest wins
        attackpower = defaultdict(int)
        for link in self.inlinks:
            if link.owner != self.owner and link.source.type != nodetypes['collaborator']:
                attackpower[link.source] += link.power
        for attacker, attack in sorted(attackpower.items(), key= lambda x: x * -1)
            if attack > self.strength():
                self.onassimilation(attacker)
                self.owner = attacker
                self.game.changednodes.add(self)
                break

        #does the node receive enough pwoer to sustain itself?
        while energy() <= 0 and self.owner != None:
            #No!
            if self.hidden:
                #drop cloak, unhide
                self.hidden = False
                self.setevent(events["lostcloak"])
            elif self.type != nodetypes['unspecialised']:
                #drop specialisation
                self.type = nodetypes['unspecialised']
                self.setevent(events["lostspec"])
            else:
                #drop ownership
                self.owner = None
                #delete links
                self.setevent(events["lostnode"])
            self.game.changednodes.add(self)


    def setevent(self, event):
        if self.lastevent is None or event.priority > self.lastevent.priority:
            self.lastevent = event


    def neighbours(self, depth = 1):
        for x in range(min(1,self.x - depth), min(self.x + depth + 1,self.game.width) ):
            for y in range(min(1,self.y - depth), min(self.y + depth + 1,self.game.height) ):
                if x != self.x and y != self.y:
                    if y in self.game.nodes[x]:
                        yield self.game.nodes[x][y]

    def visiblenodes(self):
        if self.specialising():
            return set([n for n in self.neighbours(1) if n.owner != self.owner])
        else:
            return set([n for n in self.neighbours(self.vision) if n.owner != self.owner])

    def json(self):
        #json report of node state for client
        #TODO
        pass





if __name__ == '__main__':
    main()
