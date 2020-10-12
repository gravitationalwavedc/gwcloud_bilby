import React from 'react';
import Link from 'found/lib/Link';
import { Button, Table, Badge } from 'react-bootstrap';
import InfiniteScroll from 'react-infinite-scroll-component';
import getBadgeType from './getBadgeType';

const JobTable = ({data, match, router, hasMore, loadMore, myJobs}) => {
    
    const headers = [
        {key: 'name', display: 'Name'},
        {key: 'description', display: 'Description'},
        {key: null, display: 'Status'},
        {key: null, display: 'Labels'},
        {key: null, display: 'Actions'},
    ];

    if(!myJobs){
        headers.unshift({key: 'userId', display: 'User'});
    }

    const jobRows = data.edges.length ? data.edges.map(({node}) => {
        const row = [
            node.name,
            node.description,
            <Badge 
                key={node.jobStatus ? node.jobStatus : node.jobStatus.name } 
                variant="primary" 
                pill>
                {node.jobStatus.name}
            </Badge>,
            <div key={name + '-group'}>
                {
                    node.labels.map(({name}) => 
                        <Badge 
                            key={name} 
                            variant={getBadgeType(name)} 
                            className="mr-1">
                            {name}
                        </Badge>
                    )
                }
            </div>,
            <Link 
                key={node.id}
                as={Button} 
                size="sm" 
                variant="outline-primary" 
                to={{pathname: '/bilby/job-results/' + node.id + '/'}} 
                activeClassName="selected" 
                exact 
                match={match} 
                router={router}>
                View
            </Link>
        ];

        if(!myJobs){
            row.unshift(node.user);
        }

        return row;
    }) : [];

    const headerCells = headers.map(
        ({display}) => 
            <th key={display}>{display}</th>
    );

    const rows = jobRows.length ? 
        jobRows.map((row, index) => <TableRow key={index} row={row}/>) : 
        <tr><td colSpan="6">Create a new job or try searching "Any time".</td></tr>;

    return (
        <InfiniteScroll
            dataLength={data.edges.length}
            next={loadMore}
            hasMore={hasMore}
            loader='Scroll to load more...'
        >
            <Table>
                <thead>
                    <tr>
                        {headerCells}
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </Table>
        </InfiniteScroll>
    );
};

const TableRow = ({row}) => {
    const cells = row.map((cell, index) => <td key={index}>{cell}</td>);
    return (
        <tr>
            {cells}
        </tr>
    );
};

JobTable.defaultProps = {
    myJobs: false
};

export default JobTable;
