import React from 'react';
import { HiOutlineX } from 'react-icons/hi';
import { Badge } from 'react-bootstrap';
import { getBadgeType } from '../getVariants';

const LabelBadge = ({ name, dismissable, onDismiss }) => {
    return <h5 className="d-inline ml-1">
        <Badge
            variant={getBadgeType(name)} 
            key={name} 
            pill
        >
            {name}
            {
                dismissable &&
                <a role='button' className="text-light" onClick={onDismiss}>
                    <HiOutlineX className="ml-3"/>
                </a>
            }
        </Badge>
    </h5>
}

export default LabelBadge