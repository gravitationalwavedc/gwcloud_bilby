import React from 'react';
import { Col } from 'react-bootstrap';

const JobNameCell = ({author, jobName, description}) => <Col md={6}>
    {author ? <span>{author} | </span> : null}
    <span style={{fontWeight: 700}}>{jobName}</span><br/>
    {description}
</Col>;

export default JobNameCell;
