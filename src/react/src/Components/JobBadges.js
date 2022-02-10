import React from 'react';
import { Badge } from 'react-bootstrap';
import {getBadgeType} from './getVariants';

const JobBadges = ({labels}) => 
    <React.Fragment>{labels.map(({name}) => 
        <Badge 
            key={name} 
            variant={getBadgeType(name)} 
            className="mr-1">
            {name}
        </Badge>
    )}</React.Fragment>;

export default JobBadges;
